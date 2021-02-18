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
    sequence = 1
    ICMP_ECHO_REQUEST = 8
    Destination = 999


    def packet(self,ID):
        # 1. Build ICMP header
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, 0, ID, self.sequence)
        
        # 2. Checksum ICMP packet using given function
        checksum = super().checksum(header)
        
        # 3. Insert checksum into packet by re-packing & return the packet
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, checksum, ID, self.sequence)
        return header

    def sendOnePing(self, icmpSocket, destinationAddress, ID):
        # 0. Create packet
        packet = self.packet(ID)
        
        # 1. Send packet using socket
        icmpSocket.sendto(packet,(destinationAddress,1))
        
        # 2. Record time of sending
        self.sendTime = time.time()


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
            receivedTime = time.time()

            # 3. Compare the time of receipt to time of sending, producing the total network delay
            timeComp = receivedTime - self.sendTime
            timeComp *= 1000

            # 4. Unpack the packet header for useful information, including the ID
            icmp_header = recPacket[20:28]
            size = sys.getsizeof(recPacket) 
            ttl = recPacket[8]
            
            type, code, checksum, packetID, sequence = struct.unpack('bbHHh', icmp_header)
            
            # 5. Check that the ID matches between the request and reply
            # 6. Return total network delay
            if(packetID == ID):
                
                return (timeComp,addr,self.Destination,size, ttl)
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
            # 3. Print out the returned delay (and other relevant details) using the printOneResult method
            self.printOneResult(address, packSize, timeDif, ttl)
            # 4. Continue this process until stopped
            i += 1


class Traceroute(NetworkApplication):

    sequence = 1
    ICMP_ECHO_REQUEST = 8  
    UDP_REQUEST = socket.IPPROTO_UDP
    SendingTime = 0
    ReceiveTime = 0
    TimeComparisonVal = 0
    receivedPacketNum = 0
    expectedPacketNum = 0
    Destination = 999
    timeout = 0
    socketType = ''


    def receiveOnePing(self, socket1, timeout):
        
        # 1. Wait for the socket to receive a reply
        startTime = time.time()
            
        try:

            recPacket, addr = socket1.recvfrom(1024)

        except Exception as e:
            
            socket1.close()
            return None

        # 2. Once received, record time of receipt, otherwise, handle a timeout
        self.ReceiveTime = time.time()

        # 3. Compare the time of receipt to time of sending, producing the total network delay
        self.TimeComparisonVal = (self.ReceiveTime - self.SendingTime)*1000

        # 4. Unpack the packet header for useful information, including the ID
        header = recPacket[20:28]
        size = sys.getsizeof(recPacket) - 19
        
        messagetype, code, checksum, p_id, sequence = struct.unpack('bbHHh', header)
        
        # 5. Check that the ID matches between the request and reply
        # 6. Return total network delay
        if(messagetype == 11 and code == 0): #type of ICMP response 
            
            self.receivedPacketNum += 1
            return(self.TimeComparisonVal,addr,None,size)

        elif(messagetype == 0 and code == 0):
            
            self.receivedPacketNum += 1
            return(self.TimeComparisonVal,addr,self.Destination,size)

        elif(messagetype == 3):
            
            self.receivedPacketNum += 1
            return(self.TimeComparisonVal,addr,self.Destination,size)

        else:

            return (0, 0, 0, 0)
            

    def sendOnePing(self, socket, destinationAddress, ID):
        
        # 0. Create packet
        packet = self.packet(ID)
            
        # 0.1. Attempt to flush out any existing data before closing (only done if a timeout is very very low)
        if(self.timeout < 0.5):
            
            try:
                recv, recv2 = socket.recvfrom(1024)
            except Exception as e:

                pass

            # Second attempt at receiving in case the first one timed out  
            try:
                recv, recv2 = socket.recvfrom(1024)
            except Exception as e:
                
                pass

        # 1. Send packet using socket
        if(self.socketType == 'icmp'):
            
            socket.sendto(packet,(destinationAddress,1))

        elif(self.socketType == 'udp'):
            
            socket.sendto(packet,(destinationAddress,34000))
        
        # 2. Record time of sending
        self.SendingTime = time.time()


    def packet(self,ID): #constructor for packet
                
        # 1. Build ICMP header
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, 0, ID, self.sequence)
        
        # 2. Checksum ICMP packet using given function
        checksum = self.checksum(header)
        
        # 3. Insert checksum into packet by re-packing & return the packet
        header = struct.pack("bbHHh", self.ICMP_ECHO_REQUEST, 0, checksum, ID, self.sequence)

        self.expectedPacketNum += 1
        
        return header


    def doOnePing(self, destinationAddress, timeout, ttl, ID, socketType):
        
       
        # 1. Create ICMP socket, setting the ttl and timeout
        #If the protocol type is ICMP create one ICMP socket and set the timeout using the correct methods
        if socketType == 'icmp':

            s = socket.socket(socket.AF_INET, socket.SOCK_RAW,socket.getprotobyname("icmp"))
            s.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl) #set TTL of socket
            s.settimeout(self.timeout)

        #If the protocol type is UDP 2 sockets are needed, one DGRAM socket and one RAW socket    
        else:
            
            #receiving socket 
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW,socket.getprotobyname("icmp"))
            s.settimeout(self.timeout)
            
            #sending socket
            s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,socket.getprotobyname("udp"))
            s2.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl) #set TTL of socket

        tempID = ID

        # 2. Call sendOnePing function passing a sending socket depending on protocol
        if socketType == 'icmp':
            
            self.sendOnePing(s, destinationAddress, tempID)
        else:
            
            self.sendOnePing(s2, destinationAddress, tempID)

        # 3. Call receiveOnePing function, always receive on socket s
        returnVal = self.receiveOnePing(s,self.timeout)

        # 4. Close the socket and return the delay & extra info from reciveOnePing
        s.close()

        return returnVal           
    
    def __init__(self, args):
        
        #Loading the args for traceroute (hostname, timeout, protocol)
        print('Traceroute to: %s ...' % (args.hostname), (args.timeout), (args.protocol))

        if args.timeout == None:
            args.timeout = 1

        if args.protocol == None:
            args.protocol = 'icmp'
        
        self.timeout = args.timeout
        self.socketType = args.protocol

        #If the hostname is an unresolvable address, terminate the program after printing the error which occured
        try:
            
            addressIP = socket.gethostbyname(args.hostname)
        except Exception as e:
            print(e)
            print("TERMINATING PROGRAM")
            sys.exit()

        
        self.receivedPacketNum = 0
        self.expectedPacketNum = 0

        ttl = 1
        ID = 1
        lowestTime = 0
        highestTime = 0
        avgTime = 0
        sumTime = 0
        temp = None

        while ttl < 31: #max num of hops is 30
            
            #Perform the ping operation 3 times on each ttl
            j = 0
            while j < 3:

                #Attempt to receive a response, if you dont a timeout occured 
                resp = self.doOnePing(addressIP,self.timeout,ttl, ID, self.socketType)
                if resp:
                    
                    #Unpack contents of resp into specific variables
                    delay,addr,info,size = resp 

                    if lowestTime == 0 and highestTime == 0:
                        
                        lowestTime = delay
                        highestTime = delay

                    elif lowestTime != 0 and highestTime != 0:
                        
                        if delay < lowestTime:
                            lowestTime = delay
                        elif delay > highestTime:
                            highestTime = delay
                        
                    sumTime += delay

                    try:
                        
                        hostname = socket.gethostbyaddr(addr[0]) 
                        self.printOneResult(addr[0],size,delay,ttl,hostname[0])
                    except:
                        
                        hostname = None
                        #If host name is not resolved print the address instead of the hostname
                        self.printOneResult(addr[0],size,delay,ttl,addr[0])

                else:
                    
                    print("TIMEOUT OCCURED - PACKET LOST")

                j += 1
                ID += 1

            print("-------------------------------------------------------------------------------------------")

            #Check if current address is the final address    
            if addr[0] != addressIP:
                ttl += 1
            else:
                temp = ttl
                print(f"{temp} hops completed")
                break
        
        if temp != None:
            
            avgTime = sumTime/(temp*3)
            packLoss = 100 - ((self.receivedPacketNum / self.expectedPacketNum) * 100)
            self.printAdditionalDetails(packLoss, lowestTime, avgTime, highestTime)
        
        else:
            print('MAX NUMBER OF HOPS REACHED')


class WebServer(NetworkApplication):

    hostName = "localhost"
    serverPort = 8080

    def handleRequest(self, tcpSocket, address):
        # 1. Receive request message from the client on connection socket
        request = tcpSocket.recv(1024)
        message = request.decode('utf-8').split()
        path = message[1][1:] #taking away that initial '/' character by slicing the string

        try:

            # 3. Opening the file
            f = open(path, 'r')

            # 4. Store in temporary buffer
            outputdata = f.read()
            #print(outputdata)

            header = 'HTTP/1.0 200 OK\n' #message which informs server the request was handled OK
        except IOError:

            # 5. Send the correct HTTP response error
            print("Could not read file:", path)
            outputdata = 'Error 404: File not found'
            header = 'HTTP/1.0 404 Not Found\n\n' #message informing of error, 404 file not found

        header += 'Content-Type: text/html\n\n'
        # 6. Send the content of the file to the socket
        finalOutput = header.encode()
        finalOutput += outputdata.encode()
        tcpSocket.send(finalOutput)
        print(header)
        # 7. Close the connection socket
        tcpSocket.close()
       
        pass

    def __init__(self, args):
        print('Web Server starting on port: %i...' % (args.port))
        self.serverPort = args.port
        
        # 1. Create server socket
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)
        host = socket.gethostname()

        # 2. Bind the server socket to server address and server port
        s1.bind((host, self.serverPort))

        # 3. Continuously listen for connections to server socket
        s1.listen(1)
        print(host)
        
        while True:
            newSocket, clientAddress = s1.accept()
            #http://vdi-scc203-17:1025/index.html for testing
            self.handleRequest(newSocket, clientAddress)
        
        # 5. Close server socket
        s1.close()


class Proxy(NetworkApplication):

    serverPort = 0
    cache = []
    urls = []

    def __init__(self, args):
        print('Web Proxy starting on port: %i...' % (args.port))
        
        self.serverPort = args.port
  
        #Creates the first connection sockets binding it to a host and a port, due to it being a proxy it is better to do this.
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host = socket.gethostname()
        s1.bind((host, self.serverPort))
        print("Socket has been initialized")
        
        print(host)
        print(self.serverPort)

        #Following loop allows the socket to listen for requests and call the function connect, which handles said requests, if any are to arise.
        while 1:
            
            s1.listen(1)
            try:
                conn, addr = s1.accept()
                # 1. Receive request message from the client on connection socket
                data = conn.recv(4096)
                #self.connect(conn, data, addr, s1)
                self.requestHandler(conn, data, addr)
            except KeyboardInterrupt:
                
                s1.close()
                print('Action terminated by Ctrl+C')

        s1.close()

    def requestHandler(self, tcpSocket, rawData, addr):
        
        
        # 2. Extract the path of the requested object from the message (second part of the HTTP header)

        firstTrim = rawData.decode('utf-8').split('\n')[0]

        url = firstTrim.split(' ')[1]
        
        #Removing the initial "http://" and the terminating "/" by use of find and trimming
        temp = url.find("://") + 3
        url = url[temp:-1]

        #Assigning a port
        port = 80

        #Printing out the address for debugging
        print(url)

        #If statement to ensure the addr is not in cache, if it is fetch from cache and send, if not just recv, store and send
        if url in self.urls:
            
            print("Addr is in cache. Fetching ...")
            tempIndex = self.urls.index(url)

            tcpSocket.send(str.encode('HTTP/1.0 200 OK\r\n\r\n'))
            tcpSocket.send(self.cache[tempIndex])

            data = self.cache[tempIndex]

            if(len(data) > 0):
                print(f"REQUEST DONE: {addr[0]}")
                print(f"DATA FETCHED FROM LIST INDEX {tempIndex}")
            else:
                print("REQUEST NOT DONE")

            tcpSocket.close()

        else:

            print("Addr is not in cache. Storing ...")
            proxySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # 3. Connect to socket and send the request
                proxySocket.connect((url, 80))
                proxySocket.sendall(rawData)
            
                # 4. Receive data on socket after sending request
                data = proxySocket.recv(99999)
                
                # 5. Send the correct HTTP response error
                tcpSocket.send(str.encode('HTTP/1.0 200 OK\r\n\r\n'))

                # 6. Send the content of the file to the socket
                tcpSocket.send(data)

                # 7. Close the socket
                tcpSocket.close()
                proxySocket.close()

                #Print message regarding the request (i.e is it or not done)
                if(len(data) > 0):

                    print(f"REQUEST DONE: {addr[0]}")
                else:
                    print("REQUEST NOT DONE")

            except Exception as e:
                
                print(e)
                tcpSocket.close()
                proxySocket.close()

            #Appending to cache
            self.urls.append(url)
            self.cache.append(data)

        print("-------------------------------------------------------------------------------------------") 


if __name__ == "__main__":
    args = setupArgumentParser()
    args.func(args)
