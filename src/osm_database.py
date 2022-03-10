import sys
from bz2 import BZ2File
from os.path import basename, exists
from xml.parsers.expat import ParserCreate
import time

BATCH = 1000 # Database system. Will be implemented in Version 1.5

class Node:
    def __init__(self, parent, attrs):
        self.parent = parent
        parent._parser.StartElementhander = self.start
        
        self.id = attrs['id']
        self.latitude = int(float(attrs['lat']) * 10000000)
        self.longitude = int(float(attrs['lon']) * 10000000)
        
        if 'visuble' in attrs:
            self.visible = (attrs['visible'] != 'false')
        else:
            self.visible = 1
        
        if 'action' in attrs:
            self.action = attrs['action']
        else:
            self.action = None
            self.tags = []
        
    
    def start(self, name, attrs):
        if name == 'tag':
            k = attrs['k']
            
            if k != 'created_by': self.tags.append('{0} = {1}'.format(k, attrs['v']))
    
    def end(self, name):
        self.parent._parser.EndElementHandler = self.parent.end
    
    def values(self):
        return (self.id, self.latitude, self.longitude, 1, self.visible, ';'.join(self.tags), self.parent.timestamp, 0)
    
class Way:
    def __init__(self, parent, attrs):
        self.parent = parent
        parent._parser.StartElementHandler = self.start
        
        self.id = attrs['id']
        if 'visible' in attrs:
            self.visible = (attrs['visible'] != 'false')
        else:
            self.visible = 1
        
        if 'action' in attrs:
            self.action = attrs['action']
        else:
            self.action = None
            self.nodecount = 0
        
    def start(self, name, attrs):
        if self.action != 'delete':
            if name == 'tag':
                k = attrs['k']
                if k != 'created_by':
                    self.parent.waytags.append((self.id, k, attrs['v']))
                elif name == 'nd':
                    self.nodecount += 1
                    self.parent.waynodes.append((self.id, attrs['ref'], self.nodecount))
                    self.parent._parser.EndElementHandler = self.end
    
    def end(self, name):
        self.parent._parser.EndElementHandler = self.parent.end
    
    def values(self):
        return (self.id, 1, self.parenttimestamp, self.visible)

class OSMDatabase:
    def __init__(self):
        # self. curser = curser  # Not Implemented yet. Will add databse support in Version 1.5
        self.element = None
        self.elementparser = self.start()
        self.timestamp = time.strftime('%Y%m%d%H%m%S', time.gmtime())
        self.nodes = []
        self.ways = []
        self.waytags = []
        self.waynodes = []
    
    def Parse(self, name, data):
        clock = time.clock() # Processor time
        self._parser = ParserCreate()
        self._parser.StartElementHandler = self.start
        self._parser.EndElementHandler = self.end
        self._parser.Parse(data)
        self._parser = None
        print('{0} time importing {1}'.format(time.clock() - clock, name))
    
    def ParseFile(self, name, fd):
        clock = time.clock() # Processor Time
        self._parser = ParserCreate()
        self._parser.StartElementHandler = self.start
        self._parser.EndElementHandler = self.end
        self._parser.ParseFile(fd)
        self._parser = None
        fd.close()
        print('{0} time importing {1}'.format(time.clock() - clock, name))
    
    # http://wiki.openstreetmap.org/wiki/OSM_Protocol_Version_0.5
    def start(self, name, attrs):
        if name == 'node':
            self.element = Node(self, attrs)
        elif name == 'way':
            self.element = Way(self, attrs)
    
    def end(self, name):
        if name == 'node':
            if self.element.action == 'delete':
                # Execute Database Delete. Database support starts in Version 1.5
                pass
            
            if len(self.nodes) >= BATCH:
                self.addnodes()
                self._parser.StartElementHandler = self.start
        elif name == 'way':
                if self.element.action:
                    if self.element.action =='delete':
                        pass # Delete from database. Database support starts in Version 1.5
                    else:
                        self.ways.append(self.element)
                else:
                    self.ways.append(self.element)
                    # TODO: Add in database insertion system. Database support starts in Version 1.5
        elif name =='osm':
            if self.nodses:
                self.addnodes()
            if self.ways:
                self.addways()
            if self.waytags:
                self.addwaytags()
            if self.waynodes:
                self.addwaynodes()
                
    def addnodes(self):
        # Implement inserting nodes into database. Database support starts in Version 1.5
        self.nodes = []
    
    def addways(self):
        # Implement inserting ways into database. Database support starts in Version 1.5
        self.ways = []
    
    def addwaytags(self):
        # Implement inserting waytags into database. Database support starts in Version 1.5
        self.waytags = []
    
    def addwaynodes(self):
        # Implement inserting waynodes into database. Database support starts in Version 1.5
        self.waynodes = []