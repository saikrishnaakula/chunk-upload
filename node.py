import socket
import threading
import os
import hashlib
import json
from pathlib import Path
import logging
from peerList import PeerList
import sys
import time
import math
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class Handler(PatternMatchingEventHandler):

    def __init__(self, childS, dataFolder):
        self.dataFolder = dataFolder
        self.s = childS
        PatternMatchingEventHandler.__init__(self, patterns=['*.*'],
                                             ignore_directories=True, case_sensitive=False)

    def on_any_event(self, event):
        try:
            if event.is_directory:
                return None
            else:
                self.s.sendall('updateNode'.encode())
                if self.s.recv(1024).decode() == 'file list':
                    files = os.listdir(self.dataFolder)
                    f1 = []
                    for f in files:
                        stat = os.stat(self.dataFolder / f)
                        f1.append({"name": f, "size": stat.st_size})
                    # for f in files:
                    #     f1.append(f)
                    files = str(f1)
                    files = files.encode()
                    self.s.sendall(files)
                logging.info(self.s.recv(1024).decode())
                logging.info("File updated %s." % event.src_path)
        except:
            logging.info("done")


class Node:

    def __init__(self, nodeNum, fileName):
        self.chunkSize = 1024 * 1024 
        with open("config.json") as json_data_file:
            self.config = json.load(json_data_file)
        self.dataFolder = Path(self.config['hostedFolder']) / str(nodeNum)
        logName = 'node-'+str(nodeNum) + '.log'
        logging.basicConfig(format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M', filename=Path(
                                self.config['logLocation']) / logName, filemode='w', level=logging.INFO)
        self.logger1 = logging.getLogger('node-'+str(nodeNum))
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.file_name = fileName
        self.rank = nodeNum
        self.nodeList = []
        self.nodeListMayHave = []
        self.downloadedTheFile = False
        self.acceptConnections()

    def acceptConnections(self):
        ip = socket.gethostbyname(socket.gethostname())
        self.s.bind((ip, 0))
        self.s.listen(50)
        self.port = self.s.getsockname()[1]
        self.logger1.info('Running on IP: '+ip)
        self.logger1.info('Running on port: '+str(self.port))
        threading.Thread(target=self.election).start()
        while 1:
            c, addr = self.s.accept()
            self.logger1.info('Client registered '+str(addr))
            threading.Thread(target=self.handleClient,
                             args=(c, addr,)).start()

    def handleClient(self, c, addr):
        try:
            while True:
                data = c.recv(1024).decode()
                if(data == 'registerNode'):
                    c.send('port'.encode())
                    port = int(c.recv(1024).decode())
                    self.logger1.info('Registering the node '+str(port))
                    c.send('file list'.encode())
                    files = eval(c.recv(1024).decode())
                    self.nodeList.append(
                        {'port': port, 'childPort': addr[1], 'files': files, 'active': True})
                    self.logger1.info(self.nodeList)
                    self.logger1.info('Registered the node '+str(port))
                    c.sendall('Registered successfully'.encode())
                if(data == 'updateNode'):
                    c.send('file list'.encode())
                    files = eval(c.recv(1024).decode())
                    for n in self.nodeList:
                        if n['childPort'] == addr[1]:
                            n['files'] = files
                            self.logger1.info(
                                'Updated the file list of the node '+str(n['port']))
                    self.logger1.info(self.nodeList)
                    c.sendall('Updated successfully'.encode())
                if(data == 'md5Code'):
                    c.send('fileName'.encode())
                    fileName = c.recv(1024).decode()
                    code = self.md5(self.dataFolder / fileName)
                    c.send(code.encode())
                if(data == 'listofnode'):
                    resp = []
                    c.send('port'.encode())
                    port = int(c.recv(1024).decode())
                    c.send('fileName'.encode())
                    fileName = c.recv(1024).decode()
                    self.nodeListMayHave.append(
                        {'port': port, 'childPort': addr[1], 'files': fileName, 'active': True})
                    self.logger1.info(self.nodeListMayHave)
                    for n in self.nodeList:
                        if n['active'] == True and n['childPort'] != addr[1]:
                            for l in n['files']:
                                if fileName == l['name']:
                                    resp.append(
                                        {"port": n['port'], "size": l['size']})
                        else:
                            self.logger1.info(
                                'Sent list of files to '+str(n['port']))
                    resp = str(resp)
                    resp = resp.encode()
                    c.sendall(resp)
                    c.sendall("filehash".encode())
                    c.sendall(self.md5(self.dataFolder / fileName).encode())
                    self.logger1.info('MD5 token sent to '+str(addr))
                if(data == 'electyourself'):
                    self.logger1.info('Election called by '+str(addr))
                    self.electLeader()
                if(data == 'newleader'):
                    c.sendall("port".encode())
                    if self.leader_port == self.port:
                        self.logger1.info('Leader changed '+str(self.port))
                    self.leader_port = int(c.recv(1024).decode())
                    self.logger1.info(
                        'Connecting to the new leader '+str(self.leader_port))
                    self.connectToLeader()
                if(data == 'downloadfile'):
                    c.sendall("fileName".encode())
                    data = c.recv(1024).decode()
                    filePath = self.dataFolder / data
                    fileSize = str(os.path.getsize(filePath))
                    self.logger1.info('Download requested for file ' +
                                      data + ' size ' + fileSize
                                      + ' Bytes by '+str(addr))
                    if not os.path.exists(filePath):
                        self.logger1.info(
                            'File doesnt exit '+data + ' to '+str(addr))
                        c.sendall("file-doesn't-exist".encode())
                    else:
                        c.sendall("part".encode())
                        part = int(c.recv(1024).decode())
                        self.logger1.info(
                            'Sending part '+str(part)+' of the file '+data + ' to '+str(addr))
                        if data != '':
                            tic = time.perf_counter()
                            with open(filePath, 'rb') as f:
                                f.seek((part-1)*self.chunkSize)
                                rec1 = self.chunkSize
                                if (part * self.chunkSize) > int(fileSize):
                                    rec1 = int(fileSize) - \
                                        ((part-1) * self.chunkSize)
                                fdata = f.read(rec1)
                                f.close()
                                c.sendall(fdata)
                                toc = time.perf_counter()
                                totalTime = str(f"{toc - tic:0.4f} seconds")
                                self.logger1.info(
                                    'File '+data + ' part '+str(part) + ' sent in ' + totalTime + ' to '+str(addr))
                                self.logger1.info(totalTime)
                                if c.recv(1024).decode() == 'closeTheConn':
                                    c.shutdown(socket.SHUT_RDWR)
                                    c.close()
        except:
            self.logger1.info('Connection closed for '+str(addr[1]))

    def election(self):
        NodeListFile = PeerList.getInstance().getNodes()
        listLen = len(NodeListFile)
        if listLen == 0:
            PeerList.getInstance().setNodes({
                "port": self.port,
                "leader": True,
                "rank": self.rank,
                "active": True
            })
            self.logger1.info("Leader elected "+str(self.port))
            self.leader_port = self.port
            self.connectToLeader()
        else:
            PeerList.getInstance().setNodes({
                "port": self.port,
                "leader": False,
                "rank": self.rank,
                "active": True
            })
            for e in NodeListFile:
                if e['leader'] and e["active"]:
                    try:
                        self.leader_port = e['port']
                        self.logger1.info(
                            'Connecting to the new leader '+str(self.leader_port))
                        self.connectToLeader()
                    except Exception as e:
                        self.logger1.info("done")
                        self.electLeader()

    def electLeader(self):
        NodeListFile = PeerList.getInstance().getNodes()
        noHigerRank = True
        for e in NodeListFile:
            if e['active'] and e['rank'] > self.rank:
                try:
                    childS = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    childS.connect((socket.gethostbyname(
                        socket.gethostname()), int(e['port'])))
                    childS.sendall('electyourself'.encode())
                    childS.shutdown(2)
                    childS.close()
                    noHigerRank = False
                    break
                except:
                    continue
        if noHigerRank:
            for e in NodeListFile:
                if e['port'] == self.port:
                    e['leader'] = True
                    PeerList.getInstance().setNodes(e)
                    self.leader_port = e['port']
                    self.logger1.info("Leader elected "+str(e['port']))
                    self.notifyNodes()
                    self.connectToLeader()
                    break

    def notifyNodes(self):
        NodeListFile = PeerList.getInstance().getNodes()
        for e in NodeListFile:
            if e['active']:
                try:
                    childS = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    childS.connect((socket.gethostbyname(
                        socket.gethostname()), int(e['port'])))
                    childS.sendall('newleader'.encode())
                    if childS.recv(1024).decode() == 'port':
                        childS.sendall(str(self.port).encode())
                    childS.shutdown(2)
                    childS.close()
                except:
                    e['active'] = False
                    PeerList.getInstance().setNodes(e)

    def connectToLeader(self):
        self.observer = Observer()
        self.target_ip = socket.gethostbyname(socket.gethostname())
        self.dhtConn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dhtConn.connect((self.target_ip, int(self.leader_port)))
        self.dhtConn.sendall('registerNode'.encode())
        if self.dhtConn.recv(1024).decode() == 'port':
            self.dhtConn.sendall(str(self.port).encode())
        fileList = []
        if self.dhtConn.recv(1024).decode() == 'file list':
            files = os.listdir(self.dataFolder)
            for f in files:
                stat = os.stat(self.dataFolder / f)
                fileList.append({"name": f, "size": stat.st_size})
            fileList = str(fileList)
            fileList = fileList.encode()
            self.dhtConn.sendall(fileList)
        self.logger1.info(
            'Node registered with DHT Server '+str(self.leader_port))
        self.logger1.info(self.dhtConn.recv(1024).decode())
        event_handler = Handler(self.dhtConn, self.dataFolder)
        self.observer.schedule(event_handler, self.dataFolder, recursive=True)
        self.observer.start()
        if not self.downloadedTheFile and self.file_name != '0':
            self.downloadCall()

    def getMD5(self, port, fielName):
        DownloadS = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        DownloadS.connect((self.target_ip, int(port)))
        DownloadS.sendall('md5Code'.encode())
        if DownloadS.recv(1024).decode() == 'fileName':
            DownloadS.sendall(fielName.encode())
        code = DownloadS.recv(1024).decode()
        DownloadS.shutdown(socket.SHUT_RDWR)
        DownloadS.close()
        return code

    def downloadCall(self):
        try:
            self.dhtConn.sendall('listofnode'.encode())
            if self.dhtConn.recv(1024).decode() == "port":
                self.dhtConn.sendall(str(self.port).encode())
            if self.dhtConn.recv(1024).decode() == "fileName":
                self.dhtConn.sendall(str(self.file_name).encode())
            size = 0
            dataCnt = 0
            data = self.dhtConn.recv(4098).decode()
            data = eval(data)
            dataCnt = len(data)
            size = data[0]['size']
            # if(self.dhtConn.recv(1024).decode() == "filehash"):
            hash = self.getMD5(data[0]['port'], str(self.file_name))
            self.downloadedTheFile = True
            part = math.ceil(int(size) / self.chunkSize)
            with open(self.dataFolder / self.file_name, 'wb') as f:
                f.close()
            mid = 0
            if dataCnt > 0:
                mid = part / dataCnt
            i = 1
            for d in data:
                while i <= mid:
                    self.downloadFileSingle(d["port"], i, self.file_name, size)
                    i = i+1
                while i > mid and i <= part:
                    self.downloadFileSingle(d["port"], i, self.file_name, size)
                    i = i+1
            hash2 = self.md5(self.dataFolder/self.file_name)
            if hash == hash2:
                self.logger1.info(self.file_name+' successfully downloaded.')
                print(self.file_name, 'successfully downloaded.')
            else:
                self.logger1.info(self.file_name+' unsuccessfully downloaded.')
                print(self.file_name, 'unsuccessfully downloaded.')
        except:
            self.logger1.info("done")

    def downloadFileSingle(self, port, part, file_name, size):
        try:
            DownloadS = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            DownloadS.connect((self.target_ip, int(port)))
            DownloadS.sendall('downloadfile'.encode())
            if DownloadS.recv(1024).decode() == 'fileName':
                DownloadS.sendall(file_name.encode())
            msg = DownloadS.recv(1024).decode()
            if msg == "file-doesn't-exist":
                self.logger1.info("File doesn't exist on server.")
                DownloadS.shutdown(socket.SHUT_RDWR)
                DownloadS.close()
            elif msg == 'part':
                DownloadS.sendall(str(part).encode())
                total = (part-1)*int(self.chunkSize)
                name = self.dataFolder / file_name
                with open(name, 'r+b') as file:
                    file.seek(total)
                    rec = self.chunkSize
                    if (part * self.chunkSize) > size:
                        rec = size - ((part-1) * self.chunkSize)
                    data = DownloadS.recv(rec)
                    file.write(data)
                    file.close()
                    DownloadS.sendall("closeTheConn".encode())
                    DownloadS.shutdown(socket.SHUT_RDWR)
                    DownloadS.close()
        except:
            self.logger1.info("done")

    def md5(self, name):
        hash_md5 = hashlib.md5()
        with open(name, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    # ping test every 2 mins
    def ping_test_clients(self):
        while True:
            for n in self.nodeList:
                try:
                    childS = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    childS.connect((socket.gethostbyname(
                        socket.gethostname()), int(n['port'])))
                    childS.shutdown(2)
                    childS.close()
                except:
                    n['active'] = False
            time.sleep(120)
            self.logger1.info(self.nodeList)
            # time.sleep(120.0 - ((time.time() - starttime) % 60.0))

# node = Node(9, '1.pdf')
