Network allocation REST endpoint

default base url: http://localhost:5000
    
    Reserve VLANs:
    /vlans/claim/<count>
      - Requests a contiguous set of <count> VLANs from the established pool.
        {
            "result": "success",
            "vlans": "<start>:<end>",
            "token": "<uuid_release_token>"
        }

    Release VLANs:
    /vlans/release/<uuid_release_token>
      - Releases any VLANs held by this token.
        {
            "result": "success",
        }

    Populate VLANs:
    /vlans/populate/<start>/<end>
      - Adds range of VLANs from <start> to <end> (inclusive) to the allocation pool for distribution.
        {
            "result": "success",
        }

    Reserve IPs:
    /segment/claim/<network_start_IP>-<CIDR_mask_bits>/<count>
      - Requests a contiguous set of <count> IPs from the network segment specified.
        {
            "dns": [
                "<dns1>",
                "<dns2>"
            ],
            "gateway": "10.128.0.1",
            "netmask": "255.255.0.0",
            "range": "<start_IP>:<end_IP>",
            "result": "success",
            "token": "<uuid_release_token>"
        }

    Release IPs:
    /segment/release/<uuid_release_token>
      - Releases any IPs held by this token.
        {
            "result": "success",
        }

    Populate IPs:
    /segment/populate/<network_start_IP>-<CIDR_mask_bits>/<gateway>/<dns>
      - Adds range of IPs specified by the network <network_start_IP>/<CIDR_mask_bits> to the allocation pool for distribution.
      -  This will omit the first and last IPs in the network range, as these are reserved respectively as the name and broadcast addresses of the network range.
      -  <dns> may be a comma-separated list of IPs of arbitrary length.  When an IP in this range is claimed, all will be provided in an array.
        {
            "result": "success",
        }


        
pip packages required:
- mysql-connector-python
- Flask
- SQLAlchemy

