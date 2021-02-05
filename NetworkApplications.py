#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import argparse
import socket
import os
import sys
import struct
import time
import random


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
    seq = 0
    ICMP_ECHO_REQUEST = 8
    Destination = 999


    def sendOnePing(self, icmpSocket, destinationAddress, ID):
        # 0. Create packet
        packet = self.packet(ID)
        self.seq += 1
        
        # 1. Send packet using socket
        icmpSocket.sendto(packet,(destinationAddress,1))
        
        # 2. Record time of sending
        self.sendTime = time.time()

    def packet(self,ID):
        # 1. Build ICMP header
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, 0, ID, self.seq)
        
        # 2. Checksum ICMP packet using given function
        checksum = super().checksum(header)
        
        # 3. Insert checksum into packet by re-packing & return the packet
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, checksum, ID, self.seq)
        return header

    def receiveOnePing(self, icmpSocket, destinationAddress, timeout, ID):
        # 1. Wait for the socket to receive a reply
        startTime = time.time()
        while startTime+timeout > time.time():
            
            try:
                recPacket, addr = icmpSocket.recvfrom(1024)
                #packetTemp = icmpSocket.recv(4096)
            except socket.timeout:
                break

            # 2. Once received, record time of receipt, otherwise, handle a timeout
            received_time = time.time()

            # 3. Compare the time of receipt to time of sending, producing the total network delay
            time_comp = received_time - self.sendTime
            time_comp *= 1000

            # 4. Unpack the packet header for useful information, including the ID
            icmp_header = recPacket[20:28]
            size = sys.getsizeof(recPacket) 
            ttl = recPacket[8]
            
            type, code, checksum, p_id, sequence = struct.unpack('bbHHh', icmp_header)
            
            # 5. Check that the ID matches between the request and reply
            # 6. Return total network delay
            if(p_id==ID):
                
                return (time_comp,addr,self.Destination,size, ttl)
            else:
                
                return (0, 0, 0, 0, 0)

    def doOnePing(self, destinationAddress, timeout, ID, dataDoOne):

        # 1. Create ICMP socket, setting the ttl and timeout
        ICMP_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW,socket.getprotobyname("icmp"))
        #ICMP_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl) #set ttl
        ICMP_socket.settimeout(timeout)
        packet_id = ID

        # 2. Call sendOnePing function
        self.sendOnePing(ICMP_socket, destinationAddress, packet_id)

        # 2. Call receiveOnePing function
        timeComparison, address, dest, size, ttl = self.receiveOnePing(ICMP_socket,destinationAddress,timeout, ID)

        # 3. Close the socket and return the delay
        ICMP_socket.close()
        return timeComparison, address, dest, size, ttl

    def __init__(self, args):
        print('Ping to: %s...' % (args.hostname))
        i = 0
        while i < 5:
            # 1. Look up hostname, resolving it to an IP address
            address = socket.gethostbyname(args.hostname)
            # 2. Call doOnePing function, approximately every second
            timeDif, address, dest, packSize, ttl = self.doOnePing(address, 5, i, "hiya")
            self.printOneResult(address, packSize, timeDif, ttl)
            # 3. Print out the returned delay (and other relevant details) using the printOneResult method
            #self.printOneResult(address, temp2, temp1, temp3)
            # 4. Continue this process until stopped
            i += 1


class Traceroute(NetworkApplication):

    seq = 0
    ICMP_ECHO_REQUEST = 8  
    SendingTime = 0
    ReceiveTime = 0
    Destination = 999


    def receiveOnePing(self, icmpSocket, destinationAddress, timeout):
        # 1. Wait for the socket to receive a reply
        startTime = time.time()
        while startTime+timeout > time.time():
            
            try:
                recPacket, addr = icmpSocket.recvfrom(1024)
            except socket.timeout:
                break

            # 2. Once received, record time of receipt, otherwise, handle a timeout
            received_time = time.time()

            # 3. Compare the time of receipt to time of sending, producing the total network delay
            time_comp = received_time - self.SendingTime
            time_comp = time_comp * 1000 #conversion to milliseconds

            # 4. Unpack the packet header for useful information, including the ID
            icmp_header = recPacket[20:28]
            size = sys.getsizeof(recPacket) 
            
            type, code, checksum, p_id, sequence = struct.unpack('bbHHh', icmp_header)
            
            # 5. Check that the ID matches between the request and reply
            # 6. Return total network delay
            if(type==11 and code==0): #type of ICMP response for knowing what 
                
                return(time_comp,addr,None,size)
            elif(type==0 and code==0):
                
                return(time_comp,addr,self.Destination,size)
    
            return (0, 0, 0, 0)



    def sendOnePing(self, icmpSocket, destinationAddress, ID):
        # 0. Create packet
        packet = self.packet(ID)
        self.seq += 1
        
        # 1. Send packet using socket
        icmpSocket.sendto(packet,(destinationAddress,1))
        
        # 2. Record time of sending
        self.SendingTime = time.time()

    def packet(self,ID):
        # 1. Build ICMP header
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, 0, ID, self.seq)
        
        # 2. Checksum ICMP packet using given function
        checksum = super().checksum(header)
        
        # 3. Insert checksum into packet by re-packing & return the packet
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, checksum, ID, self.seq)
        return header

    def doOnePing(self, destinationAddress, timeout,ttl, ID):
        
        # Option to choose UDP or ICMP for extra marks
        # 1. Create ICMP socket, setting the ttl and timeout
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW,socket.getprotobyname("icmp"))
        s.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl) #set ttl
        s.settimeout(timeout)
        packet_id = ID

        # 2. Call sendOnePing function
        self.sendOnePing(s, destinationAddress, packet_id)

        # 2. Call receiveOnePing function
        delay = self.receiveOnePing(s,destinationAddress,timeout)

        # 3. Close the socket and return the delay
        s.close()
        return delay

    def getHostname(self,addr):
        if(addr==None):
            return None
        else:
             try:
                 host=socket.gethostbyaddr(addr[0])   
                 return host     
             except:
                 return None  

    def printResult(self,delay,addr,size,ttl):
        
        if(delay==0 and addr==0):
            print("Timeout")
            return     
        
        hostname = self.getHostname(addr)
        
        if(hostname==None):
            super().printOneResult(addr[0],size,delay,ttl,"UNABLE TO RESOLVE HOST NAME")
        else:
            super().printOneResult(addr[0],size,delay,ttl,hostname[0])
               
    
    def __init__(self, args):
        
        print('Traceroute to: %s...' % (args.hostname))
        
        timeout = 10
        address_ip = socket.gethostbyname(args.hostname)
        prev_address = None
        
        ttl = 1
        ID = 1
        while ttl < 31: #max num of hops is 30
            
            j = 0
            while j < 3:
                    
                resp = self.doOnePing(address_ip,timeout,ttl, ID)
                if resp:
                    delay,addr,info,size = self.doOnePing(address_ip,timeout,ttl, ID)
                    self.printResult(delay,addr,size,ttl)
                    j += 1
                    ID += 1
                else:
                    print("NO RESPONSE")

            print("-------------------------------------------------------------------------------------------")
        
            if prev_address != addr:
                prev_address = addr
                ttl +=1
            else:
                break


class WebServer(NetworkApplication):

    hostName = "localhost"
    serverPort = 8080

    def handleRequest(self, tcpSocket, address):
        # 1. Receive request message from the client on connection socket
          
        request = tcpSocket.recv(1024).decode('utf-8')
        string_list = request.split('\n')[0].split(' / ')
        
        print(request)

        # 2. Extract the path of the requested object from the message (second part of the HTTP header)

        method = string_list[0] # First string is a method
        requesting_file = string_list[1] #Second string is request file
        
        print('Client method ', method)
        print('Client request ', requesting_file)
        
        tcpSocket.close()
        
        #filename = receivedPacket.decode("utf-8").split('\r\n')[0] 
        #sliced = filename[6:]

        #print('\n')
        #print(sliced)

        # 3. Read the corresponding file from disk

        f = open(requesting_file[0:8], 'rb')
        print(f)

        # 4. Store in temporary buffer

        outputdata = f.read()
        print(outputdata)
        
        # 5. Send the correct HTTP response error

        #tcpSocket.send("HTTP/1.1 200 OK\r\n\r\n")
        
        # 6. Send the content of the file to the socket


        #for i in range(0, len(outputdata)):
        #    tcpSocket.send(outputdata[i])
        #tcpSocket.send("\r\n")

        # 7. Close the connection socket

        #tcpSocket.close()
        pass

    def __init__(self, args):
        print('Web Server starting on port: %i...' % (args.port))
        # 1. Create server socket
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)
        host = socket.gethostname()
        # 2. Bind the server socket to server address and server port
        s1.bind((host,1025))
        # 3. Continuously listen for connections to server socket
        s1.listen(1)
        print(host)
        
        while True:
            newSocket, clientAddress = s1.accept()
            #http://vdi-scc203-17:1025/
            self.handleRequest(newSocket, clientAddress)
        
        # 5. Close server socket


class Proxy(NetworkApplication):

    def __init__(self, args):
        print('Web Proxy starting on port: %i...' % (args.port))


if __name__ == "__main__":
    args = setupArgumentParser()
    args.func(args)
