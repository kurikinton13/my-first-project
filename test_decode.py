import json, base64, zlib, re

sample = 'jQuery112009470403170287213_1782547468123({"status":"middle","data":"eNqlvduqLUmTpfcqIq93J34+1KuIQjSqbiiQ6Av1XVPv3hFh3/CwuWxCsVJ/QVJ7xlge7uaH8GHH//XX//jv//3f/+9//6//z//1b//1f/rf/ua//+Wvf/mrpDL+Sxr/pcz/I49/yf1f0vrrz1//49/+7f/+6l/+11+Z//yff/W/91//Spon+7ea8v2ePv"})'
m = re.match(r'jQuery\d+_\d+\((.*)\)$', sample)
data = json.loads(m.group(1))
print(f'status: {data["status"]}')
print(f'compress: {data.get("compress","0")}')
print(f'reason: {data["reason"]}')
print(f'data length: {len(data["data"])}')
# decompress
if data.get('data'):
    compressed = base64.b64decode(data['data'])
    decompressed = zlib.decompress(compressed)
    odds_json = json.loads(decompressed.decode('utf-8'))
    print(f"\nDecompressed keys: {list(odds_json.keys())}")
    if 'odds' in odds_json:
        print(f"odds count: {len(odds_json['odds'])}")
        for h, horses in odds_json['odds'].items():
            for h_id, info in horses.items():
                print(f"  horse {h_id}: {info}")
