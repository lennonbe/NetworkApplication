#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import argparse
import socket
import os
import sys
import struct
import time


def setupArgumentParser() -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description='A collection of Network Applications developed for SCC.203.')
        parser.set_defaults(func=ICMPPing, hostname='lancaster.ac.uk')
        subparsers = parser.add_subparsers(help='sub-command help')
        
        parser_p = subparsers.add_parser('ping', aliases=['p'], help='run ping')
        parser_p.add_argument('hostname', type=str, help='host to ping towards')
        parser_p.add_argument('count', nargs='?', type=int,
                              help='number of times to ping the host before stopping')
        parser_p.add_argument('timeout', nargs='?',
                              type=int,
                              help='maximum timeout before considering request lost')
        parser_p.set_defaults(func=ICMPPing)

        parser_t = subparsers.add_parser('traceroute', aliases=['t'],
                                         help='run traceroute')
        parser_t.add_argument('hostname', type=str, help='host to traceroute towards')
        parser_t.add_argument('timeout', nargs='?', type=int,
                              help='maximum timeout before considering request lost')
        parser_t.add_argument('protocol', nargs='?', type=str,
                              help='protocol to send request with (UDP/ICMP)')
        parser_t.set_defaults(func=Traceroute)

        parser_w = subparsers.add_parser('web', aliases=['w'], help='run web server')
        parser_w.set_defaults(port=8080)
        parser_w.add_argument('port', type=int, nargs='?',
                              help='port number to start web server listening on')
        parser_w.set_defaults(func=WebServer)

        parser_x = subparsers.add_parser('proxy', aliases=['x'], help='run proxy')
        parser_x.set_defaults(port=8000)
        parser_x.add_argument('port', type=int, nargs='?',
                              help='port number to start web server listening on')
        parser_x.set_defaults(func=Proxy)

        args = parser.parse_args()
        return args


class NetworkApplication:

    def checksum(self, dataToChecksum: str) -> str:
        csum = 0
        countTo = (len(dataToChecksum) // 2) * 2
        count = 0

        while count < countTo:
            thisVal = dataToChecksum[count+1] * 256 + dataToChecksum[count]
            csum = csum + thisVal
            csum = csum & 0xffffffff
            count = count + 2

        if countTo < len(dataToChecksum):
            csum = csum + dataToChecksum[len(dataToChecksum) - 1]
            csum = csum & 0xffffffff

        csum = (csum >> 16) + (csum & 0xffff)
        csum = csum + (csum >> 16)
        answer = ~csum
        answer = answer & 0xffff
        answer = answer >> 8 | (answer << 8 & 0xff00)

        answer = socket.htons(answer)

        return answer

    def printOneResult(self, destinationAddress: str, packetLength: int, time: float, ttl: int, destinationHostname=''):
        if destinationHostname:
            print("%d bytes from %s (%s): ttl=%d time=%.2f ms" % (packetLength, destinationHostname, destinationAddress, ttl, time))
        else:
            print("%d bytes from %s: ttl=%d time=%.2f ms" % (packetLength, destinationAddress, ttl, time))

    def printAdditionalDetails(self, packetLoss=0.0, minimumDelay=0.0, averageDelay=0.0, maximumDelay=0.0):
        print("%.2f%% packet loss" % (packetLoss))
        if minimumDelay > 0 and averageDelay > 0 and maximumDelay > 0:
            print("rtt min/avg/max = %.2f/%.2f/%.2f ms" % (minimumDelay, averageDelay, maximumDelay))


class ICMPPing(NetworkApplication):

    sendTime = 0
    arrivalTime = 0


    def sendOnePing(self, icmpSocket, destinationAddress, ID):
        # 1. Build ICMP header
        ICMP_ECHO = 8
        checksum = 0
        header = struct.pack("BBHHH", 8, 0, checksum, ID, 1) #!BBHHH is the format of the header struct
        # header = struct.pack("BBHHH", ICMP_ECHO, 0, checksum, ID, 1)
        data = struct.pack("d", time.time())
        # 2. Checksum ICMP packet using given function
        checksum = super().checksum(header + data)
        # 3. Insert checksum into packet
        header = struct.pack("BBHHH", 8, 0, checksum, ID, 1)
        #header = struct.pack("BBHHH", ICMP_ECHO, 0, checksum, ID, 1)
        # 4. Send packet using socket
        icmpSocket.sendto(header, (destinationAddress, socket.getprotobyname('icmp')))
        # 5. Record time of sending
        sendTime = time.time()

        return sendTime

    def receiveOnePing(self, icmpSocket, destinationAddress, ID, timeout, timeVar):
        # 1. Wait for the socket to receive a reply
        # receivedPacket = icmpSocket.recvfrom(1024)
        # icmpHeader = receivedPacket[0][20:28]

        while True:
            receivedPacket = icmpSocket.recv(4096)
            print(receivedPacket)
            if receivedPacket:
                # 2. Once received, record time of receipt, otherwise, handle a timeout
                arrivalTime = time.time()
                break

        # 3. Compare the time of receipt to time of sending, producing the total network delay
        timeComparison = arrivalTime - timeVar
        ttp = receivedPacket[8]
        packetSize = sys.getsizeof(receivedPacket)
        # print(timeComparison)
        # 4. Unpack the packet header for useful information, including the ID
        icmpHeader = receivedPacket[20:28]
        typeOf, code, checksum, p_id, sequence = struct.unpack('bbHHh', icmpHeader)
        print(typeOf)
        print(code)
        print(checksum)
        print(p_id)
        # 5. Check that the ID matches between the request and reply
        if p_id != ID:
            return -1
        # 6. Return total network delay
        return timeComparison, packetSize, ttp

    def doOnePing(self, destinationAddress, timeout, ID):
        # 1. Create ICMP socket
        s = socket.socket(socket.AF_INET,socket.SOCK_RAW, socket.IPPROTO_ICMP)
        # 2. Call sendOnePing function
        # temp = self.sendOnePing(s, socket.gethostbyname(destinationAddress), ID)
        temp = self.sendOnePing(s, destinationAddress, ID)
        # 3. Call receiveOnePing function
        # timeDif = self.receiveOnePing(s, socket.gethostbyname(destinationAddress), ID, timeout, temp)
        timeDif, packSize, ttpValue = self.receiveOnePing(s, destinationAddress, ID, timeout, temp)
        # 4. Close ICMP socket
        s.close()
        # 5. Return total network delay
        if timeDif == -1:
            print("error")
        else:
            print("Total network delay is:")
            print(timeDif * 1000)

        return timeDif * 1000, packSize, ttpValue
        pass

    def __init__(self, args):
        print('Ping to: %s...' % (args.hostname))
        # 1. Look up hostname, resolving it to an IP address
        address = socket.gethostbyname(args.hostname)
        # 2. Call doOnePing function, approximately every second
        temp1, temp2, temp3 = self.doOnePing(address, 1000, 1)
        # 3. Print out the returned delay (and other relevant details) using the printOneResult method
        #self.printOneResult('1.1.1.1', 50, 20.0, 150) # Example use of printOneResult - complete as appropriate
        self.printOneResult(address, temp2, temp1, temp3)
        # 4. Continue this process until stopped


class Traceroute(NetworkApplication):

    def __init__(self, args):
        # Please ensure you print each result using the printOneResult method!
        print('Traceroute to: %s...' % (args.hostname))


class WebServer(NetworkApplication):

    def handleRequest(tcpSocket):
        # 1. Receive request message from the client on connection socket
        # 2. Extract the path of the requested object from the message (second part of the HTTP header)
        # 3. Read the corresponding file from disk
        # 4. Store in temporary buffer
        # 5. Send the correct HTTP response error
        # 6. Send the content of the file to the socket
        # 7. Close the connection socket
        pass

    def __init__(self, args):
        print('Web Server starting on port: %i...' % (args.port))
        # 1. Create server socket
        # 2. Bind the server socket to server address and server port
        # 3. Continuously listen for connections to server socket
        # 4. When a connection is accepted, call handleRequest function, passing new connection socket (see https://docs.python.org/3/library/socket.html#socket.socket.accept)
        # 5. Close server socket


class Proxy(NetworkApplication):

    def __init__(self, args):
        print('Web Proxy starting on port: %i...' % (args.port))


if __name__ == "__main__":
    args = setupArgumentParser()
    args.func(args)
