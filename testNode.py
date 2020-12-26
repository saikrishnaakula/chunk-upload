from node import Node
import sys
from peerList import PeerList

# clearing the peer list
PeerList.getInstance()

nodeNum = int(sys.argv[1])
if(nodeNum-1 == 0):
    file = '0'
else:
    file = str(nodeNum-1)+'.pdf'
client = Node(nodeNum,file)
