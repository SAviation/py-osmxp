from math import cos, floor, pi, radians
from os.path import basename, dirname, exists
from struct import unpack
from dsf_errors import ErrorNoAtoms, ErrorPoolOutOfRange, BadCommand

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
        lines = [{} for i in range (BUCKETS  * BUCKETS)]
        tris = [[] for i in range(BUCKETS * BUCKETS)]
        
        # Open dsf file and read it.
        dsfInfo = open(dsf_path, 'rb')
        
        # Check to see if the dsfInfo is what we need.
        if dsfInfo.read(8).decode() != 'XPLNEDSF' or unpack('<I', dsfInfo.read(4)) != (1,) or dsfInfo.read(4).decode() != 'DAEH':
            # Raise Invalid DSF as it is not what we need.
            raise ErrorNoAtoms
        
        # Unpack some data
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        
        # Find the end of the header information
        headerEnd = dsfInfo.tell() + unpackDSF - 8
        
        if dsfInfo.read(4).decode() != 'PORP':
            raise ErrorNoAtoms
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        
        dsfHeader = dsfInfo.read(unpackDSF - 9).split(b'\0')
        
        dsfInfo.read(1)
        
        is_overlay = 0
        
        for i in range(0, len(dsfHeader) - 1, 2):
            # is the header info about the overlay?
            if dsfHeader[i].decode() == 'sim/overlay':
                overlay = int(dsfHeader[i + 1])\
            
            # is the header info about south tile?
            if dsfHeader[i].decode() == 'sim/south': 
                tileSouth = int(dsfHeader[i + 1])
            
            # is the header info about west tile?
            if dsfHeader[i].decode() == 'sim/west': 
                tileWest = int(dsfHeader[i + 1])
        
        # We only want mesh data. raise IsOverlay if greater than 0
        if is_overlay > 0:
            raise Exception
        
        centralLat = tileSouth + 0.5
        centralLon = tileWest + 0.5
        
        # Jump to the end of the Header.
        dsfInfo.seek(headerEnd)
        
        # Definitions Atom
        if dsfInfo.read(4).decode() != 'NFED':
            raise ErrorNoAtoms
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        atomEnd = dsfInfo.tell() + unpackDSF - 8
        
        # Grab data about terrain, objects, polygons and networks
        while dsfInfo.tell() < atomEnd:
            dsfAtom = dsfInfo.read(4)
            (unpackDSF,) = unpack('<I', dsfInfo.read(4))
            if unpackDSF == 8:
                # unpacked info is empty
                pass
            elif dsfAtom.decode() == 'TRET':
                terrain = dsfInfo.read(unpackDSF - 9).replace(b'\\', b'/').replace(b':',b'/').split(b'\0')
                dsfInfo.read(1)
            elif dsfAtom.decode() == 'TJBO':
                objects = dsfInfo.read(unpackDSF - 9).replace(b'\\', b'/').replace(b':',b'/').split(b'\0')
                dsfInfo.read(1)
            elif dsfAtom.decode() == 'YLOP':
                polygons = dsfInfo.read(unpackDSF - 9).replace(b'\\', b'/').replace(b':',b'/').split(b'\0')
                dsfInfo.read(1)
            elif dsfAtom.decode() == 'WTEN':
                networks = dsfInfo.read(unpackDSF - 9).replace(b'\\', b'/').replace(b':',b'/').split(b'\0')
                dsfInfo.read(1)
            else:
                dsfInfo.seek(unpackDSF - 8, 1)
        
        # If its not the Geodata Atom let's raise InvalidDSF
        if dsfInfo.read(4).decode() != 'DOEG':
            raise ErrorNoAtoms
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        
        # Find the end of Geodata
        geoEnd = dsfInfo.tell() + unpackDSF - 8
        pool = []
        scal = []
        
        while dsfInfo.tell() < geoEnd:
            dsfGeo = dsfInfo.read(4)
            (unpackDSF, ) = unpack('<I', dsfInfo.read(4))
            if dsfGeo.decode() == 'LOOP':
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
                                for j in range(r&127):
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
                        raise ErrorPoolOutOfRange
                    current_pool.append(current_plane)
                pool.append(current_pool)
            elif dsfGeo.decode() == 'LACS':
                scal.append([unpack('<2f', dsfInfo.read(8)) for i in range(0, unpackDSF - 8, 8)])
            else:
                dsfInfo.seek(unpackDSF - 8, 1)
        if len(pool) != len(scal):
            raise ErrorPoolOutOfRange
        
        for i in range(len(pool)):
            current_pool = pool[i]
            num_pool_entries = len(current_pool[0]) # Number of entries in this pool
            new_pool = [[] for j in range(num_pool_entries)]
            for plane in range(len(current_pool)):
                (scale, offset) = scal[i][plane]
                scale = scale / 0xffff
                for j in range(num_pool_entries):
                    new_pool[j].append(current_pool[plane][j] * scale + offset)
            pool[i] = new_pool
        
        # Commands Atom
        if dsfInfo.read(4).decode() != 'SDMC':
            raise ErrorNoAtoms
        
        (unpackDSF,) = unpack('<I', dsfInfo.read(4))
        cmd_end = dsfInfo.tell() + unpackDSF - 8
        current_pool = None
        net_base = 0
        cmd_index = 0
        near = 0
        far = -1
        flags = 0 # 1 = physical, 2 = overlay
        current_terrain = 0
        
        while dsfInfo.tell() < cmd_end:
            (cmd,) = unpack('<B', dsfInfo.read(1))
            if cmd == 1:
                # Coordinate Pool Select
                current_pool = pool[unpack('<H', dsfInfo.read(2))[0]]
            elif cmd == 2:
                # Junction Offset Select
                dsfInfo.read(4) # Not Implemented Yet
            elif cmd == 3:
                # Set Definition
                (cmd_index,) = unpack('<B', dsfInfo.read(1))
            elif cmd == 4:
                # Set Definition
                (cmd_index,) = unpack('<H', dsfInfo.read(2))
            elif cmd == 5:
                # Set Definition
                (cmd_index,) = unpack('<I', dsfInfo.read(4))
            elif cmd == 6:
                # Set Road Subtype
                dsfInfo.read(1) # Not Implemented Yet
            elif cmd == 7:
                # Object
                dsfInfo.read(2) # Not Implemented Yet
            elif cmd == 8:
                # Object Range
                dsfInfo.read(4) # Not Implemented Yet
            elif cmd == 9:
                # Network Chain
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                dsfInfo.read(unpackDSF * 2) # Not Implemented Yet
            elif cmd == 10:
                # Network Chain Range
                dsfInfo.read(4) # Not Implemented
            elif cmd == 11:
                # Network Chain 32bit
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                dsfInfo.read(unpackDSF * 2) # Not Implemented Yet
            elif cmd == 12:
                # Polygon
                (param, unpackDSF) = unpack('<HB', dsfInfo.read(3))
                dsfInfo.read(unpackDSF * 2) # Not Implemented
            elif cmd == 13:
                # Polygon Range (DSF2Text uses this one)
                (param, first, line) = unpack('<HHH', dsfInfo.read(6)) # Not Implemented
            elif cmd == 14:
                # Nested Polygon
                (param, n) = unpack('<HB', dsfInfo.read(3))
                for i in range(n):
                    (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                    dsfInfo.read(unpackDSF * 2) # Not Implemented Yet
            elif cmd == 15:
                # Nested Polygon Range (DSF2Text uses this one too)
                (param, n) = unpack('<HB', dsfInfo.read(3))
                dsfInfo.read((n + 1) * 2 ) # Not Implemented Yet
            elif cmd == 16:
                # Terrian Patch
                current_terrain = cmd_index
            elif cmd == 17:
                # Terrain Patch w/ flags
                (flags,) = unpack('<B', dsfInfo.read(1))
                current_terrain = cmd_index
            elif cmd == 18:
                # Terrain Patch w/ Flags & LOD
                (flags, near, far) = unpack('<Bff', dsfInfo.read(9))
                current_terrain = cmd_index
            elif cmd == 19:
                # Not Defined
                pass
            elif cmd == 20:
                # Not Defined
                pass
            elif cmd == 21:
                # Not Defined
                pass
            elif cmd == 22:
                # Not Defined
                pass
            elif cmd == 23:
                # Patch Triangles
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                if not flags & 1:
                    dsfInfo.read(2 * unpackDSF)
                else:
                    for i in range(0, unpackDSF, 3):
                        points = []
                        for j in range(3):
                            (d,) = unpack('<H', dsfInfo.read(2))
                            points.append(current_pool[d])
                        tri = Tri(current_terrain, *points)
                        for bucket in tri.buckets(tileWest, tileSouth):
                            tris[bucket].append(tri)
                        for j in range(3):
                            line = Line(points[j], points[(j + 1) % 3])
                            for bucket in line.buckets(tileWest, tileSouth):
                                lines[bucket][line] = True
            elif cmd == 24:
                # Patch Triangles - Cross Pool
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                if not flags & 1:
                    dsfInfo.read(4 * unpackDSF)
                else:
                    for i in range(0, unpackDSF, 3):
                        points = []
                        for j in range(3):
                            (p, d) = unpack('<HH', dsfInfo.read(4))
                            points.append(pool[p][d])
                        tri = Tri(current_terrain, *points)
                        for bucket in tri.buckets(tileWest, tileSouth):
                            tris[bucket].append(tri)
                        for j in range(3):
                            line = Line(points[j], points[(j + 1) % 3])
                            for bucket in line.buckets(tileWest, tileSouth):
                                lines[bucket][line] = True
            elif cmd == 25:
                # Patch Triangle Range
                (first, last) = unpack('HH', dsfInfo.read(4))
                if flags & 1:
                    for i in range(first, last, 3):
                        tri = Tri(current_terrain, *current_pool[i:i + 3])
                        for bucket in tri.buckets(tileWest, tileSouth):
                            tris[bucket].append(tri)
                        for j in range(3):
                            line = Line(current_pool[i + j], current_pool[i + (j + 1) %3])
                            for bucket in line.buckets(tileWest, tileSouth):
                                lines[bucket][line] = True
            elif cmd == 26:
                # Patch Triangle Strip (used by g2xpl and MeshTool)
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                if not flags & 1:
                    dsfInfo.read(2 * unpackDSF)
                else:
                    points = []
                    for i in range(unpackDSF):
                        (d,) = unpack('<H', dsfInfo.read(2))
                        points.append(current_pool[d])
                    for i in range(unpackDSF - 2):
                        if i % 2:
                            tri = Tri(current_terrain, points[i + 2], points[i + 1], points [i])
                        else:
                            tri=Tri(current_terrain, points[i], points[i + 1], points[i + 2])
                            for bucket in tri.buckets(tileWest, tileSouth):
                                tris[bucket].append(tri)
                            for line in [Line(points[i], points[i + 1]), Line(points[i], points[i + 2])]:
                                for bucket in line.buckets(tileWest, tileSouth):
                                    lines[bucket][line] = True
                    line = Line(points[unpackDSF - 2], points[unpackDSF - 1]) # Last Line
                    for bucket in line.buckets(tileWest, tileSouth):
                        lines[bucket][line] = True
            elif cmd == 27:
                # Patch Triangle Strip - Cross Pool
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                if not flags & 1:
                    dsfInfo.read(4 * unpackDSF)
                else:
                    points = []
                    for i in range(unpackDSF):
                        (p, d) = unpack('<HH', dsfInfo.read(4))
                        points.append(pool[p][d])
                    for i in range(unpackDSF - 2):
                        if i % 2:
                            tri = Tri(current_terrain, points[i + 2], points[i + 1], points[i])
                        else:
                            tri = Tri(current_terrain, points[i], points[i + 1], points[i + 2])
                            for bucket in tri.buckets(tileWest, tileSouth):
                                tris[bucket].append(tri)
                            for line in [Line(points[i], points[i + 1]), Line(points[i], points[i + 2])]:
                                for bucket in line.buckets(tileWest, tileSouth):
                                    lines[bucket][line] = True
                    line = Line(points[unpackDSF - 2], points[unpackDSF - 1]) # Last Line
                    for bucket in line.buckets(tileWest, tileSouth):
                        lines[bucket][line] = True
            elif cmd == 28:
                # Patch Triangle Strip Range
                (first, last) = unpack('<HH', dsfInfo.read(4))
                if flags & 1:
                    points = current_pool[first:last]
                    unpackDSF = last - first
                    for i in range(unpackDSF - 2):
                        if i % 2:
                            tri = Tri(current_terrain, points[ i + 2], points[i + 1], points[i])
                        else:
                            tri = Tri(current_terrain, points[i], points[ i + 1], points[i + 2])
                            for bucket in tri.buckets(tileWest, tileSouth):
                                tris[bucket].append(tri)
                            for line in [Line(points[i], points[i + 1]), Line(points[i], points[i + 2])]:
                                for bucket in line.buckets(tileWest, tileSouth):
                                    lines[bucket][line] = True
                    line = Line(points[unpackDSF - 2], points[unpackDSF -1]) # last line
                    for bucket in line.buckets(tileWest, tileSouth):
                        lines[bucket][line] = True
            elif cmd == 29:
                # Patch Triangle Fan
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                if not flags & 1:
                    dsfInfo.read(2 * unpackDSF)
                else:
                    points = []
                    for i in range(unpackDSF):
                        (d,) = unpack('<H', dsfInfo.read(2))
                        points.appded(current_pool[d])
                    for i in range(1, unpackDSF - 1):
                        tri = Tri(current_terrain, points[0], points[i], points[ i + 1])
                        for bucket in tri.buckets(tileWest, tileSouth):
                            tris[bucket].append(tri)
                        for line in [Line(points[0], points[i]), Line(points[i], points[i + 1])]:
                            for bucket in line.buckets(tileWest, tileSouth):
                                lines[bucket][line] = True
                    line = Line(points[0], points[unpackDSF - 1]) # Last line
                    for bucket in line.buckets(tileWest, tileSouth):
                        lines[bucket][line] = True
            elif cmd == 30:
                # Patch Triangle Fan - Cross Pool
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                if not flags & 1:
                    dsfInfo.read(4 * unpackDSF)
                else:
                    points = []
                    for i in range(unpackDSF):
                        (p,d) = unpack('<HH', dsfInfo.read(4))
                        points.append(pool[p][d])
                    for i in range(1, unpackDSF - 1):
                        tri = Tri(current_terrain, points[0], points[i], points[i + 1])
                        for bucket in tri.buckets(tileWest, tileSouth):
                            tris[bucket].append(tri)
                        for line in [Line(points[0], points[i]), Line(points[i], points[i + 1])]:
                            for bucket in line.buckets(tileWest, tileSouth):
                                lines[bucket][line] = True
                    line = Line(points[0], points[unpackDSF - 1]) # Last line
                    for bucket in line.buckets(tileWest, tileSouth):
                        lines[bucket][line] = True
            elif cmd == 31:
                # Patch Triangle Fan Range
                (first, last) = unpack('<HH', dsfInfo.read(4))
                if flags & 1:
                    for i in range(first, last -1):
                        tri = Tri(current_terrain, current_pool[first], current_pool[i], current_pool[i + 1])
                        for bucket in tri.buckets(tileWest, tileSouth):
                            tris[bucket].append(tri)
                        for line in [Line(current_pool[first], current_pool[i]), Line(current_pool[i], current_pool[i + 1])]:
                            for bucket in line.buckets(tileWest, tileSouth):
                                lines[bucket][line] = True
                    line = Line(current_pool[first], current_pool[last - 1]) # Last line
                    for bucket in line.buckets(tileWest, tileSouth):
                        lines[bucket][line] = True
            elif cmd == 32:
                # Comments
                (unpackDSF,) = unpack('<B', dsfInfo.read(1))
                dsfInfo.read(unpackDSF)
            elif cmd == 33:
                # Comments
                (unpackDSF,) = unpack('<H', dsfInfo.read(2))
                dsfInfo.read(unpackDSF)
            elif cmd == 34:
                # Comments
                (unpackDSF,) = unpack('<I', dsfInfo.read(4))
                dsfInfo.read(unpackDSF)
            else:
                # Unknown Command
                raise BadCommand
        
        # Convert lines to lists
        lines = [bucket.keys() for bucket in lines]
        
        return(lines, tris)
        
    except IOError:
        pass

if __name__ == '__main__':
    lines, tris = readDSF(r'C:\Program Files (x86)\Steam\steamapps\common\X-Plane 11\Global Scenery\X-Plane 11 Demo Areas\Earth nav data\+20-160\+20-156\+20-156.dsf')
    for tri in tris:
        print(tri)
