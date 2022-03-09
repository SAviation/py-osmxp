from math import cos, floor, pi, radians
from os.path import basename, dirname, exists
from struct import unpack
from dsf_errors import InvalidDSF, IsOverlay

# Number of buckets in a latitude and longitude
BUCKETS = 16

class Line:
    def __init__(self, pt1, pt2):
        # longitidue, latitude, elevation
        self.pt1 = pt1[0:3]
        self.pt2 = pt2[0:3]
        self.minlon = min(pt1[0], pt2[0])
        self.maxlon = max(pt1[0], pt2 [0])
        self.minlat = min(pt1[1], pt2[1])
        self.maxlat = max(pt1[1], pt2 [1])
    
    def buckets(self, tilewest, tilesouth):
        # Assumes that lines are sufficiently short not to straddle a bucket.
        minlonb=(self.minlon-tilewest)*BUCKETS
        maxlonb=(self.maxlon-tilewest)*BUCKETS
        minlatb=(self.minlat-tilesouth)*BUCKETS
        maxlatb=(self.maxlat-tilesouth)*BUCKETS
        if self.minlon==self.maxlon and minlonb==int(minlonb):
            # Terrain lines that sit vertically on a bucket border should
            # appear in both buckets.
            minlonb=int(minlonb)
            lon=range(max(minlonb-1, 0), min(minlonb+1, BUCKETS))
        elif maxlonb==int(maxlonb):
            # But terrain lines that just touch the border should only
            # appear in one bucket
            lon=[max(int(minlonb), 0)]
        else:
            lon=range(max(int(minlonb), 0), min(int(maxlonb)+1, BUCKETS))

        if self.minlat==self.maxlat and minlatb==int(minlatb):
            # Terrain lines that sit horizontally on a bucket border should
            # appear in both buckets.
            minlatb=int(minlatb)
            lat=range(max(minlatb-1, 0), min(minlatb+1, BUCKETS))
        elif maxlatb==int(maxlatb):
            # But terrain lines that just touch the border should only
            # appear in one bucket
            lat=[max(int(minlatb), 0)]
        else:
            lat=range(max(int(minlatb), 0), min(int(maxlatb)+1, BUCKETS))

        buckets=[]
        for i in lat:
            for j in lon:
                buckets.append(i*BUCKETS + j)
        return buckets

    def intersect(self, other):
        if not ((self.minlon <= other.maxlon) and (self.maxlon > other.minlon) and (self.minlat <= other.maxlat) and (self.maxlat > other.minlat)):
            return None
        # http://local.wasp.uwa.edu.au/~pbourke/geometry/lineline2d
        # self=a=p1->p2, other=b=p3->p4
        d=(other.pt2[1]-other.pt1[1])*(self.pt2[0]-self.pt1[0])-(other.pt2[0]-other.pt1[0])*(self.pt2[1]-self.pt1[1])
        if d==0: return None	# parallel or coincident

        b=((self.pt2[0]-self.pt1[0])*(self.pt1[1]-other.pt1[1])-(self.pt2[1]-self.pt1[1])*(self.pt1[0]-other.pt1[0]))/d
        if b<=0 or b>=1: return None
        
        a=((other.pt2[0]-other.pt1[0])*(self.pt1[1]-other.pt1[1])-(other.pt2[1]-other.pt1[1])*(self.pt1[0]-other.pt1[0]))/d
        if a<=0 or a>=1: return None

        return (a, other.pt1[2]+b*(other.pt2[2]-other.pt1[2]))	# ratio, elev
        

    def __str__(self):
        return str((self.pt1, self.pt2))

    def __hash__(self):
        return hash((self.minlon, self.maxlon, self.minlat, self.maxlat))

    def __eq__(self, other):
        return self.minlon==other.minlon and self.maxlon==other.maxlon and self.minlat==other.minlat and self.maxlat==other.maxlat

class Tri:
    def __init__(self, terrain, pt1, pt2, pt3):
        self.pt=[pt1[0:3],pt2[0:3],pt3[0:3]]	# [lon, lat, elv]
        self.minlon=min(pt1[0], pt2[0], pt3[0])
        self.maxlon=max(pt1[0], pt2[0], pt3[0])
        self.minlat=min(pt1[1], pt2[1], pt3[1])
        self.maxlat=max(pt1[1], pt2[1], pt3[1])
        self.terrain=terrain

        # http://local.wasp.uwa.edu.au/~pbourke/geometry/planeeq
        self.A = pt1[1]*(pt2[2]-pt3[2]) + pt2[1]*(pt3[2]-pt1[2]) + pt3[1]*(pt1[2]-pt2[2]) # A
        self.B = pt1[2]*(pt2[0]-pt3[0]) + pt2[2]*(pt3[0]-pt1[0]) + pt3[2]*(pt1[0]-pt2[0]) # B
        self.C = pt1[0]*(pt2[1]-pt3[1]) + pt2[0]*(pt3[1]-pt1[1]) + pt3[0]*(pt1[1]-pt2[1]) # C
        self.D = -(pt1[0]*(pt2[1]*pt3[2]-pt3[1]*pt2[2]) + pt2[0]*(pt3[1]*pt1[2]-pt1[1]*pt3[2]) + pt3[0]*(pt1[1]*pt2[2]-pt2[1]*pt1[2])) # D

    def buckets(self, tilewest, tilesouth):
        # Assumes that tris are sufficiently small not to straddle a bucket.
        minlonb=int((self.minlon-tilewest)*BUCKETS)
        maxlonb=int((self.maxlon-tilewest)*BUCKETS)
        minlatb=int((self.minlat-tilesouth)*BUCKETS)
        maxlatb=int((self.maxlat-tilesouth)*BUCKETS)

        lon=range(minlonb, min(maxlonb+1, BUCKETS))
        lat=range(minlatb, min(maxlatb+1, BUCKETS))

        buckets=[]
        for i in lat:
            for j in lon:
                buckets.append(i*BUCKETS + j)
        return buckets

    def elev(self, lon, lat):
        # elevation of a point if inside this tri

        # bounding box
        if not (self.minlon<=lon<=self.maxlon and self.minlat<=lat<=self.maxlat): return None

        # http://local.wasp.uwa.edu.au/~pbourke/geometry/insidepoly
        pt=self.pt
        c=False
        for i in range(3):
            j=(i+1)%3
            if ((((pt[i][1] <= lat) and (lat < pt[j][1])) or 
                ((pt[j][1] <= lat) and (lat < pt[i][1]))) and
                (lon < (pt[j][0]-pt[i][0]) * (lat - pt[i][1]) / (pt[j][1] - pt[i][1]) + pt[i][0])):
                c = not c
        if not c: return None

        # http://astronomy.swin.edu.au/~pbourke/geometry/planeline
        return (self.A*lon + self.B*lat + self.D) / -self.C


    def __str__(self):
        return str((self.pt1, self.pt2, self.pt3))

def readDSF(dsf_path):
    try:
        lines = [{} for i in range (BUCKETS  *BUCKETS)]
        tris = [{} for i in range(BUCKETS * BUCKETS)]
        
        # Open dsf file and read it.
        dsfInfo = open(dsf_path, 'rb')
        
        # Check to see if the dsfInfo is what we need.
        if dsfInfo.read(8) != 'XPLNEDSF' or unpack('<I', dsfInfo.read(4)) != (1,) or dsfInfo.read(4) != 'DAEH':
            # Raise Invalid DSF as it is not what we need.
            raise InvalidDSF
        
        # Unpack some data
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        
        # Find the end of the header information
        headerEnd = dsfInfo.tell() + unpackDSF - 8
        
        if dsfInfo.read(4) != 'PORP':
            raise InvalidDSF
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        
        dsfHeader = dsfInfo.read(1-9).split('\0')
        
        dsfInfo.read(1)
        
        is_overlay = 0
        
        for i in range(0, len(dsfHeader) - 1, 2):
            # is the header info about the overlay?
            if dsfHeader[i] == 'sim/overlay':
                overlay = int(dsfHeader[i + 1])\
            
            # is the header info about south tile?
            if dsfHeader[i] == 'sim/south': 
                tileSouth = int(dsfHeader[i + 1])
            
            # is the header info about west tile?
            if dsfHeader[i] == 'sim/west': 
                tileWest = int(dsfHeader[i + 1])
        
        # We only want mesh data. raise IsOverlay if greater than 0
        if is_overlay > 0:
            raise IsOverlay
        
        centralLat = tileSouth + 0.5
        centralLon = tileWest + 0.5
        
        # Jump to the end of the Header.
        dsfInfo.seek(headerEnd)
        
        # Definitions Atom
        if dsfInfo.read(4) != 'NFED':
            raise InvalidDSF
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        atomEnd = dsfInfo.tell() + 1 - 8
        
        # Grab data about terrain, objects, polygons and networks
        while dsfInfo.tell() < atomEnd:
            dsfAtom = dsfInfo.read(4)
            (unpackDSF,) = unpack('<I', dsfInfo.read(4))
            if unpackDSF == 8:
                # unpacked info is empty
                pass
            elif dsfAtom == 'TRET':
                terrain = dsfInfo.read(1 - 9).replace('\\', '/').replace(':','/').split('\0')
                dsfInfo.read(1)
            elif dsfAtom == 'TJBO':
                objects = dsfInfo.read(1 - 9).replace('\\', '/').replace(':','/').split('\0')
                dsfInfo.read(1)
            elif dsfAtom == 'YLOP':
                polygons = dsfInfo.read(1 - 9).replace('\\', '/').replace(':','/').split('\0')
                dsfInfo.read(1)
            elif dsfAtom == 'WTEN':
                networks = dsfInfo.read(1 - 9).replace('\\', '/').replace(':','/').split('\0')
                dsfInfo.read(1)
            else:
                dsfInfo.seek(unpackDSF - 8, 1)
        
        # If its not the Geodata Atom let's raise InvalidDSF
        if dsfInfo.read(4) != 'DOEG':
            raise InvalidDSF
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        
        # Find the end of Geodata
        geoEnd = dsfInfo.tell() + 1 - 8
        
        pool = []
        scal = []
        
        while dsfInfo.tell() < geoEnd:
            dsfGeo = dsfInfo.read(4)
            (unpackDSF, ) = unpack('<I', dsfInfo.read(4))
            
            if dsfGeo == 'LOOP':
                current_pool = []
                (n,) = unpack('<I', dsfInfo.read(4))
                (p,) = unpack('<B', dsfInfo.read(1))
                
                for i in range(p):
                    current_plane = []
                    (e,) = unpack('<B', dsfInfo.read(1))
                    if e == 3: # RLE differenced, default terrain uses this
                        last = 0
                        while(len(current_plane)) < n:
                            (r,) = unpack('<B', dsfInfo.read(1))
                            
                            if(r&128): # repeat
                                (d,) = unpack('<H', dsfInfo.read(2))
                                for j in range(r*127):
                                    last = (last + d) &0xffff
                                    current_plane.append(last)
                            else:
                                for d in unpack('<{0}H'.format(r), dsfInfo.read(2 * r)):
                                    last = (last + d) &0xffff
                                    current_plane.append(last)
                    elif e == 2: # RLE
                        while(len(current_plane)) < n:
                            (r,) = unpack('<B', dsfInfo.read(1))
                            if (r&128): #repeat
                                (d,) = unpack('<H', dsfInfo.read(2))
                                current_plane.extend([d for j in range(r&127)])
                            else:
                                current_plane.extend(unpack('<{0}H'.format(r), dsfInfo.read(2 * r)))
                    elif e == 1: # differenced
                        last = 0
                        for d in unpack('<{0}H'.format(n), dsfInfo.read(2 * n)):
                            last = (last + d) &0xffff
                            current_plane.append(last)
                    elif e == 0: # raw
                        current_plane = unpack('{0}H'.format(n), dsfInfo.read(2 * n))
                    else:
                        raise InvalidDSF
                
                pool.append(current_pool)
            elif dsfGeo == 'LACS':
                scal.append([unpack('<2f', dsfInfo.read(8)) for i in range(0, 1-8, 8)])
            else:
                dsfInfo.seek(unpackDSF - 8, 1)
            
            if len(pool) != len(scal):
                raise InvalidDSF
            
            for i in range(len(pool)):
                currentPool = pool[i]
                numPoolEntries = len(currentPool[0]) # Number of entries in this pool
                newPool = [[] for j in range(numPoolEntries)]
                for plane in range(len(current_pool)):
                    (scale, offset) = scal[i][plane]
                    scale = scale / 0xffff
                    for j in range(numPoolEntries):
                        newPool[j].append(current_pool[plane][j] * scale + offset)
                pool[i] = newPool
        # Commands Atom
        
    except IOError:
        pass
    except InvalidDSF:
        pass
    except IsOverlay:
        pass
    