import socket
import threading
import os
import hashlib
import json
from pathlib import Path
import sys
import time
import math

size = os.path.getsize('4.pdf')
chunkSize = 1024 * 1024
print(size)
def getData(j):
    with open('4.pdf', 'rb') as f:
        f.seek((j-1)*int(chunkSize))
        rec1 = chunkSize
        if (j * chunkSize) > size:
             rec1 = size - ((j-1) * chunkSize)
        print(rec1)
        data = f.read(rec1)
        f.close()
        return data


part = math.ceil(size / chunkSize)
with open('1.pdf', 'wb') as f:
        f.close()
i = 1
name = '1.pdf'
while i <= part:
    total = (i-1)*int(chunkSize)
    with open(name, 'r+b') as file:
        file.seek(total)
        rec = chunkSize
        print(i)
        if (i * chunkSize) > size:
            rec = size - ((i-1) * chunkSize)
        print(rec)
        data = getData(i)
        file.write(data)
        file.close()
        i = i+1
                

