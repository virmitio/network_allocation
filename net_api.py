import json
import uuid
from flask import Flask
app = Flask(__name__)
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import sys

# Magic Variables section
#    create_engine requires a connection string in the format:
#       "<database_engine>+<DB_driver>://<user>:<password>@<DB_hostname>/<Database_name>"
engine = create_engine("mysql+mysqlconnector://api:api_password@localhost/api_db", encoding='latin1', echo=True)
# End Magic Variables section


def int_to_ip(ip_int):
    oct4 = ip_int % 256
    rem = ip_int >> 8
    oct3 = rem % 256
    rem = rem >> 8
    oct2 = rem % 256
    # Need to modulo the last octet to avoid negative values.
    oct1 = (rem >> 8) % 256
    return "{0}.{1}.{2}.{3}".format(oct1, oct2, oct3, oct4)

def ip_to_int(ip):
    octs = ip.split('.')
    if len(octs) < 4:
        return 0
    return (int(octs[0])<<24)+(int(octs[1])<<16)+(int(octs[2])<<8)+int(octs[3])

def get_ranges(size, set):
    new = ""
    range_len = len(set)
    a = lambda x, y: " %s:%s " % (x, y) if (y - x) >= (size-1) else " "
    
    for i in xrange(range_len):
        if i == 0:
            start = set[i]
            end = set[i]
        else:
            delta = set[i] - set[i-1]
            if (delta != 1) or (end-start) >= size:
                new += (a(start, end))
                start = set[i]
                end = set[i]
            else:
                end = set[i]
    else:
        if range_len == (i + 1):
            new += (a(start, end))
            
    return new.split()

def ip_context_func(context):
    return int_to_ip(context.current_parameters['ip_int'])

def calculate_network(network):
    # Split the network into the start and end based on the size (eg. /16)
    #  The first and last IPs in the network are removed from the pool,
    #  as they represent the entire network and the broadcast addresses respectively.
    tmp = network.split('-')
    start = ip_to_int(tmp[0]) + 1
    size = 32-int(tmp[1])
    net = 0
    for i in xrange(size):
        net = (net << 1) + 1
    end = (((start-1) >> size) << size) + net
    return {"start": start, "end": end, "mask": (net^-1)}

Session = sessionmaker(bind=engine)
AlchemyBase = declarative_base()

class IP_Record(AlchemyBase):
    __tablename__ = 'ip_list'
    ip_int = Column(Integer, primary_key=True, autoincrement=False)
    ip = Column(String(15), default=ip_context_func)
    gateway = Column(String(15))
    dns = Column(String(100))
    mask = Column(Integer)
    token = Column(String(36), default=None)
    
class VLAN_Record(AlchemyBase):
    __tablename__ = 'vlan_list'
    vlan = Column(Integer, primary_key=True)
    token = Column(String(36), default=None)

@app.route('/')
def hello_world():
    return 'Hello World!'

@app.route('/vlans/claim/<count>', methods=['POST'])
def allocate_vlans(count):
    cnt = int(count)
    token = uuid.uuid4() #our token for claiming/releasing VLANs.
    current = Session()
    try:
        rquery = current.query(VLAN_Record).filter(VLAN_Record.token.is_(None)).order_by(VLAN_Record.vlan)
        rtmp = []
        for i in rquery.all():
            rtmp += [i.vlan]
        ranges = get_ranges(cnt, rtmp)
        for r in ranges:
            # Get the min of the range
            low = int((r.split(':'))[0])
            high = low + (cnt-1)
            q = current.query(VLAN_Record).filter(VLAN_Record.vlan >= low).filter(VLAN_Record.vlan <= high)
            if q.filter(VLAN_Record.token.isnot(None)).count() > 0:
                # Missed our window on this range, move on to the next.
                continue
            else:
                # This set still unclaimed, set the token and return the range and token as a JSON object.
                q.update({VLAN_Record.token: str(token)}, synchronize_session="fetch")
                current.commit()
                return json.dumps({'result': 'success', 'vlans': str(low)+':'+str(high), 'token': str(token)}, sort_keys=True, indent=4, separators=(',', ': '))
        
        # If we hit this, we've run out of ranges to try and couldn't allocate the VLANs requested.  Return an "empty" result.
        current.close()
        return json.dumps({'result': 'failure - unable to allocate', 'vlans': '0:0', 'token': none}, sort_keys=True, indent=4, separators=(',', ': '))
    except:
        current.close()
        print(sys.exc_info()[:2])
        return json.dumps({'result': 'failure - exception thrown'}, sort_keys=True, indent=4, separators=(',', ': '))

@app.route('/vlans/release/<ident_token>', methods=['POST'])
def release_vlans(ident_token):
    # Clears the token data from any VLAN assigned to the provided ident_token.
    current = Session()
    try:
        current.query(VLAN_Record).filter(VLAN_Record.token.like(ident_token)).update({"token": None}, synchronize_session="fetch")
        current.commit()
        return json.dumps({'result': 'success'}, sort_keys=True, indent=4, separators=(',', ': '))
    except:
        current.close()
        print(sys.exc_info()[:2])
        return json.dumps({'result': 'failure - exception thrown'}, sort_keys=True, indent=4, separators=(',', ': '))

@app.route('/vlans/populate/<start>/<end>', methods=['POST'])
def populate_vlans(start, end):
    current = Session()
    try:
        # Loop through and add the VLAN records to the current transaction.  Commit at end of loop.
        for x in xrange(int(start),int(end)+1):
            current.add(VLAN_Record(vlan=x))
        else:
            current.commit()
            return json.dumps({'result': 'success'}, sort_keys=True, indent=4, separators=(',', ': '))
    except:
        current.close()
        print(sys.exc_info()[:2])
        return json.dumps({'result': 'failure - exception thrown'}, sort_keys=True, indent=4, separators=(',', ': '))

@app.route('/segment/claim/<network>/<count>', methods=['POST'])
def allocate_segment(network,count):
    cnt = int(count)
    token = uuid.uuid4() #our token for claiming/releasing network segments (IPs).
    net = calculate_network(network)
    current = Session()
    try:
        rquery = current.query(IP_Record).filter(IP_Record.token.is_(None)).filter(IP_Record.ip_int >= net["start"]).filter(IP_Record.ip_int <= net["end"]).order_by(IP_Record.ip_int)
        rtmp = []
        for i in rquery.all():
            rtmp += [i.ip_int]
        ranges = get_ranges(cnt, rtmp)
        for r in ranges:
            # Get the min of the range
            low = int((r.split(':'))[0])
            high = low + (cnt-1)
            q = current.query(IP_Record).filter(IP_Record.ip_int >= low).filter(IP_Record.ip_int <= high)
            if q.filter(IP_Record.token.isnot(None)).count() > 0:
                # Missed our window on this range, move on to the next.
                continue
            else:
                # This set still unclaimed, set the token and return the range and token as a JSON object.
                q.update({IP_Record.token: str(token)}, synchronize_session="fetch")
                tmp_obj = q.first()
                netmask = int_to_ip(tmp_obj.mask)
                gateway = tmp_obj.gateway
                dns = tmp_obj.dns.split(',')
                current.commit()
                return json.dumps({'result': 'success', 'range': int_to_ip(low)+':'+int_to_ip(high), 'netmask': netmask,'gateway': gateway,'dns': dns, 'token': str(token)}, sort_keys=True, indent=4, separators=(',', ': '))
        
        # If we hit this, we've run out of ranges to try and couldn't allocate the IPs requested.  Return an "empty" result.
        current.close()
        no_ip = '0.0.0.0'
        return json.dumps({'result': 'failure - unable to allocate', 'range': no_ip+':'+no_ip, 'netmask': no_ip, 'gateway': no_ip, 'dns': [no_ip], 'token': none}, sort_keys=True, indent=4, separators=(',', ': '))
    except:
        current.close()
        print(sys.exc_info()[:2])
        return json.dumps({'result': 'failure - exception thrown'}, sort_keys=True, indent=4, separators=(',', ': '))
    
@app.route('/segment/release/<ident_token>', methods=['POST'])
def release_segment(ident_token):
    # Clears the token data from any IP assigned to the provided ident_token.
    current = Session()
    try:
        current.query(IP_Record).filter(IP_Record.token.like(ident_token)).update({"token": None}, synchronize_session="fetch")
        current.commit()    
        return json.dumps({'result': 'success'}, sort_keys=True, indent=4, separators=(',', ': '))
    except:
        current.close()
        print(sys.exc_info()[:2])
        return json.dumps({'result': 'failure - exception thrown'}, sort_keys=True, indent=4, separators=(',', ': '))

@app.route('/segment/populate/<network>/<gateway>/<dns>', methods=['POST'])
def populate_segment(network,gateway,dns):
    net = calculate_network(network)
    
    current = Session()
    try:
        flush_counter = 0
        # Loop through and add the IP records to the current transaction.  Commit at end of loop.
        for x in xrange(net["start"],net["end"]):
            flush_counter += 1
            current.add(IP_Record(ip_int=x, gateway=gateway, dns=dns, mask=net["mask"]))
            # Periodic flush to avoid a connection error for flushing large data sets
            if flush_counter >= 20000:
                flush_counter = 0
                current.flush()
        else:
            current.commit()
            return json.dumps({'result': 'success'}, sort_keys=True, indent=4, separators=(',', ': '))
    except:
        current.close()
        print(sys.exc_info()[:2])
        return json.dumps({'result': 'failure - exception thrown'}, sort_keys=True, indent=4, separators=(',', ': '))

if __name__ == '__main__':
    AlchemyBase.metadata.create_all(engine)
    app.run()
