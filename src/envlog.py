import pandas as pd
from datetime import timedelta, datetime as dt, timezone
import datetime as dt
import time
from urllib.request import urlopen
import json
import math
import traceback

def envlog(telnr, dateObs, utc):
    '''
    Gets weather/env data from tcsu archiver.
    '''

    #define archiver api url
    hostname = f'k{telnr}epicsgateway'
    port = 17668
    url = f'http://{hostname}:{port}/retrieval/data/getData.json?'

    #calc start and end period using +/- interval
    utDatetime = dt.datetime.strptime(dateObs + ' ' + utc, '%Y-%m-%d %H:%M:%S.%f')
    interval = 30
    dt1 = utDatetime + dt.timedelta(seconds=-interval)
    dt1 = dt1.strftime('%Y-%m-%dT%H:%M:%SZ')
    dt2 = utDatetime + dt.timedelta(seconds=interval)
    dt2 = dt2.strftime('%Y-%m-%dT%H:%M:%SZ')

    #map keywords for KOA to archiver channels
    keymap = { 
        'wx_dewpoint'    : f'k0:met:dewpointRaw',           
        'wx_outhum'      : f'k0:met:humidityRaw',           
        'wx_outtmp'      : f'k0:met:tempRaw',               
        'wx_domtmp'      : f'k{telnr}:met:tempRaw',       
        'wx_domhum'      : f'k{telnr}:met:humidityRaw',   
        'wx_pressure'    : f'k0:met:pressureRaw',           
        'wx_windspeed'   : f'k{telnr}:met:windSpeedRaw',  
        'wx_winddir'     : f'k{telnr}:met:windAzRaw',   
        'guidfwhm'       : f'k{telnr}:dcs:pnt:cam0:fwhm'  
    }

    #defaults for return data dict
    data = {}
    data['wx_time'] = 'null'
    data['fwhm_time'] = 'null'

    #get channel data from archive for each pv
    errors = []
    warns = []
    mn = None
    for kw, pv in keymap.items():
        data[kw] = 'null'

        try:
            #query archiver api and make sure we found some records
            sendUrl = f'{url}pv={pv}&from={dt1}&to={dt2}'
            d = urlopen(sendUrl).read().decode('utf8')
            d = json.loads(d)
            if not d or len(d) == 0:
                warns.append(f"No data for {pv}")
                continue
            d = d[0].get('data')
            if not d:
                warns.append(f"No records for {pv}")
                continue

            #find closest entry in time
            ts_utc = utDatetime.replace(tzinfo=dt.timezone.utc).timestamp()
            entry = find_closest_entry(d, ts_utc)
            if entry is None:
                warns.append(f"No recent records found for {pv}")
                continue
            data[kw] = entry['val']

            #tack on decimal seconds from nanos
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(entry['secs']))
            nanos = str(entry['nanos'])[0:2]
            ts = f"{ts}.{nanos}"

            #mark closest time
            if kw == 'guidfwhm': data['fwhm_time'] = ts[-11:]
            else:
                diff = abs(entry['secs'] - ts_utc)
                if mn == None or diff < mn:
                    data['wx_time'] = ts[-11:]
                    mn = diff

        except Exception as e:
            errors.append(f"{pv}:{traceback.format_exc()}")
            #errors.append(f"{pv}:{str(e)}")

    return data, errors, warns


def find_closest_entry(entries, ts):
    mn = None
    best = None
    for e in entries:
        diff = abs(e['secs'] - ts)
        if mn == None or diff < mn:
            mn = diff
            best = e
    return best

