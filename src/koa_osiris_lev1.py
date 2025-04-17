import argparse
from astropy.io import fits
from astropy.wcs import WCS
from astropy import units as u
import datetime as dt
import db_conn
from getpass import getuser
import matplotlib.pyplot as plt
from matplotlib import colors
import numpy as np
from os import walk, makedirs, chdir, remove
from os.path import isdir, isfile, basename, dirname
import requests
from shutil import copyfile
from socket import gethostname
import sys
from time import sleep
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
import yaml
import json
import gzip
import shutil
import logging


class KoaOsirisDrp(FileSystemEventHandler):
    '''
    Handles the directory monitoring and processing of data.
    '''

    def __init__(self, instrument, datadir, outputdir, rti):

        self.running  = True
        self.whoami   = getuser()
        self.hostname = gethostname()
        self.rti      = rti

        self.instrument      = instrument
        self.datadir         = datadir
        self.outputdir       = outputdir

        self.log = self.create_logger()
        self.log.info(f'Monitoring {self.datadir}')
        self.log.info(f'RTI outputdir is {self.outputdir}')
        self.log.info(f'RTI API is {self.rti}')

        self.dpi = 100

        self.queue         = []
        self.fileList      = []

        self.add_current_file_list()


    def create_logger(self):
        """Creates a logger"""

        # Create logger object
        name = f'koa_osiris_lev1'
        log = logging.getLogger(name)
        log.setLevel(logging.DEBUG)

        # paths
        logFile =  f'/log/{name}.log'

        # Create a file handler
        handle = logging.FileHandler(logFile)
        handle.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handle.setFormatter(formatter)
        log.addHandler(handle)

        # add stdout to output so we don't need both log and print statements(>= warning only)
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s - %(message)s')
        sh.setFormatter(formatter)
        log.addHandler(sh)

        # init message and return
        log.info(f'logger created at {logFile}')
        return log


    def on_any_event(self, event):
        '''
        Callback to add new files to the queue.
        '''

        if event.is_directory:
            return

        # Skip if not a created event
        if event.event_type != 'created':
            return

        # Check the base filename
        filename = basename(event.src_path)
        if not filename.endswith('.fits') or filename in self.fileList:
            return

        self.log.info(f'on_any_event {event.src_path}')
        filename = event.src_path

        if filename in self.fileList:
            self.log.info('Skipping - already processed')
            return

        self.queue.append(filename)


    def add_current_file_list(self):
        '''
        Loops through and adds any files currently located in self.datadir
        to the queue.
        '''

        for root, dirs, files in walk(self.datadir):
            files.sort()
            for file in files:
                if not file.endswith('.fits'):
                    continue
                filename = f'{root}/{file}'
                self.queue.append(filename)

        self.running = False


    def process_current_file_list(self):
        '''
        Processes all files in the queue, then empties the queue.
        '''

        self.running = True

        while len(self.queue) > 0:
            filename = self.queue[0]
            self.db = db_conn.db_conn('config.live.ini', configKey='DATABASE', persist=True)
            self.process_file(filename)
            self.db.close()
            self.fileList.append(filename)
            self.queue.remove(filename)

        self.running = False


    def process_file(self, filename):
        '''
        Processes a file depending on its type.
        '''

        self.log.info(f'Input file {filename}')

        hdr  = fits.getheader(filename)
        datafile = hdr['DATAFILE']
        self.log.info(f'DATAFILE is {datafile}')

        # Is this file in koa_staus?
        query = f"select * from koa_status where ofname like '%{datafile}' and koaimtyp='object' and level=0"
        row = self.db.query('koa', query, getOne=True)
        if row is False:
            self.log.info(f'lev0 "object" file not in koa_status for {filename}')
            self.handle_error('DATABASE_ERROR', query)
            return

        if len(row) == 0:
            self.log.info(f'lev0 "object" file not in koa_status for {filename}')
            return

        # Verify lev0 was actually archived
        koaid = row['koaid']
        status = row['status']
        processdir = row['process_dir']
        print(f'{koaid} {status} {processdir}')
        self.log.info(f'Found koa_status entry for {koaid}')
        if status != 'COMPLETE':
            self.log.info(f'lev0 "object" file not archived for {filename}/{koaid}')
            return

        # Does lev1 entry already exist?
        query = f"select * from koa_status where koaid='{koaid}' and level=1"
        row = self.db.query('koa', query, getOne=True)
        if len(row) != 0:
            self.log.info(f'lev1 entry exists in koa_status for {filename}/{koaid}')
            return

        rtiFile = f'{processdir}/{koaid}.fits'
        if not isfile(rtiFile):
            self.log.info(f'lev0 file does not exist ({rtiFile})')
            return

        hdr  = fits.getheader(rtiFile)
        koaid    = hdr['KOAID']
        semester = hdr['SEMESTER']
        koaimtyp = hdr['KOAIMTYP']
        progid   = hdr['PROGID']
        proginst = hdr['PROGINST']
        progpi   = hdr['PROGPI']
        progtl1  = hdr['PROGTL1']
        progtl2  = hdr['PROGTL2']
        progtl3  = hdr['PROGTL3']
        self.log.info(f'{semester} {progid} {proginst} {progpi}')

        # Copy the file and log to outputdir
        origfile = basename(filename)
        newfile = f'{self.outputdir}/{origfile}'
        self.log.info(f'Copying {filename} to {newfile}')
        copyfile(filename, newfile)
        origfile = f"{dirname(filename)}/DRFs/{datafile.replace('.fits', '_ORP.log')}"
        if isfile(origfile):
            logfile = f"{self.outputdir}/{koaid.replace('.fits', '.lev1.log')}"
            self.log.info(f'Copying {origfile} to {logfile}')
            copyfile(origfile, logfile)

        try:
            img  = fits.open(newfile, ignore_missing_end=True)
        except:
            self.log.info(f'Error reading file {newfile}')
            return
        hdr  = img[0].header
        data = img[0].data

        # Add PROG* info from koa_status/headers
        hdr.set('KOAID',    koaid)
        hdr.set('SEMESTER', semester)
        hdr.set('KOAIMTYP', koaimtyp)
        hdr.set('DATLEVEL', 1)
        hdr.set('PROGID',   progid)
        hdr.set('PROGINST', proginst)
        hdr.set('PROGPI',   progpi)
        hdr.set('PROGTL1',  progtl1)
        hdr.set('PROGTL2',  progtl2)
        hdr.set('PROGTL3',  progtl3)

        # Create a new FITS file and JPG of the data
        newfile = f"{self.outputdir}/{koaid.replace('.fits', '.lev1.fits')}"
        self.log.info(f'Creating new FITS file ({newfile})')
        img.writeto(newfile, overwrite=True)

        # gzip the FITS file
        self.log.info(f'gzipping FITS file ({newfile})')
        gzipFile = f'{newfile}.gz'
        with open(f'{newfile}', 'rb') as fIn:
            with gzip.open(gzipFile, 'wb', compresslevel=1) as fOut:
                shutil.copyfileobj(fIn, fOut)
        remove(f'{newfile}')

        self.create_ql_image(newfile, hdr, data)

        # Call the RTI API
        if self.rti == True:
            try:
                koaid = hdr['KOAID']
                url = f'{self.rtiUrl}instrument={self.instrument}&koaid={koaid}&ingesttype=lev1&datadir={self.outputdir}'
                self.log.info(f'Notifying RTI of successful reduction ({url})')
                resp = requests.get(url, auth=(self.rtiUser, self.rtiPwd))
            except:
                self.log.info(f'Error with {url}')

        img.close()

        return

    def create_ql_image(self, newfile, hdr, data):
        '''
        Creates the quicklook JPG image of the data cube.
        '''

        # Create JPG
        newfile = newfile.replace('.fits', '.jpg')
        self.log.info(f'Creating QL JPG file ({newfile})')

        # Get WCS information
        try:
            wcs = WCS(hdr)
        except:
            wcs = None

        # Find the peak wavelength slice
        peak = previousMax = 0
        try:
            slices = data.shape
            wave = hdr['CRVAL1']
            for i in range(slices[2]):
                max = np.max(data[:,:,i])
                if max > previousMax:
                    peak = i
                previousMax = max
            wave = wave + (hdr['CDELT1'] * (peak+1))
            self.log.info(f'Peak wavelength slice at {peak}/{wave}')
        except:
            return

        plt.figure(figsize=(12,6))
        plt.subplots_adjust(wspace=1.25)

        for i in range(1, 4):
            plt.subplot(1,3,i, projection=wcs, slices=(0,'y','x'))
            if i == 1:
                image_data = np.sum(data, axis=2)
                title = 'SUM'
            if i == 2:
                image_data = np.median(data, axis=2)
                title = 'MEDIAN'
            if i == 3:
                image_data = data[:,:,peak]
                title = f'PEAK ({wave} nm)'
            plt.imshow(image_data.transpose(), cmap='gray', norm=colors.PowerNorm(0.6))
            plt.colorbar()
            plt.xlabel('Right Ascension')
            plt.ylabel('Declination')
            plt.title(title)
            x = plt.gca().coords[2]
            x.set_major_formatter('hh:mm:ss.ss')
            x.set_ticks(spacing=0.30 * u.arcsecond)

        plt.savefig(newfile)
        plt.close()


def main():
    instrument = 'OSIRIS'

    parser = argparse.ArgumentParser(description='OSIRIS SPEC Quicklook DRP')
    parser.add_argument('--rti', dest='rti', default=False, action='store_true',
                        help='Notify RTI upon each successful reduction')
    parser.add_argument('--utdate', type=str, help='UT date to process',
                        default=dt.datetime.utcnow().strftime('%Y-%m-%d'))
    parser.add_argument('--manual', dest='manual', default=False,
                        action='store_true',
                        help='Manual run, disable end hour')
    args = parser.parse_args()
    rti = args.rti

    utdate = dt.datetime.strptime(args.utdate, '%Y-%m-%d')
    tonight = (utdate - dt.timedelta(days=1)).strftime('%Y-%m-%d')

    # Change dir for access to configuration file
    chdir(sys.path[0])

    # Get config
    if isfile('config.live.ini'):
        with open('config.live.ini') as f:
            config = yaml.safe_load(f)
    else:
        print('config.live.ini file not found')
        exit()

    # Is OSIRIS scheduled for the night?  Get account being used.
    try:
        url  = config['API']['MAIN']
        url = f'{url}/schedule/getSchedule?date={tonight}&instr={instrument}'
        resp = requests.get(url)
        response = json.loads(resp.text)
        if len(response) == 0:
            print(f'{instrument} is not scheduled for {tonight}')
            exit()
        else:
            account = response[0]['Account']
    except:
        print(f'Unknown if {instrument} is on sky tonight')
        exit()

    # Set datadir to monitor
    utdateStr  = utdate.strftime('%y%m%d')
    datadir    = f'/s/sdata1100/{account}/{utdateStr}/SPEC/ORP'

    # Set RTI outputdir
    utdateStr = utdate.strftime('%Y%m%d')
    root      = config[instrument]['ROOTDIR']
    outputdir = f'{root}/{instrument}/{utdateStr}/lev1'

    hourStart = int(dt.datetime.utcnow().strftime('%H'))

    # Wait for datadir to appear
    endHour = 17 if not args.manual else 24
    while not isdir(datadir):
        hourNow = int(dt.datetime.utcnow().strftime('%H'))
        if hourNow >= endHour:
            print('Night is over - goodbye')
            exit()
        print(f'Waiting for directory ({datadir}) to appear')
        sleep(60)
    if datadir.endswith('/'):
        datadir = datadir[:-1]

    # Create outputdir, if needed
    if outputdir.endswith('/'):
        outputdir = outputdir[:-1]
    if not isdir(outputdir):
        makedirs(outputdir)

    # Setup monitoring of directory
    event_handler = KoaOsirisDrp(instrument, datadir, outputdir, rti)
    observer = PollingObserver(30)
    observer.schedule(event_handler, path=datadir, recursive=False)
    observer.start()

    if rti == True:
        try:
           event_handler.rtiUrl  = config['RTI']['API']
           event_handler.rtiUser = config['RTI']['USER']
           event_handler.rtiPwd  = config['RTI']['PWD']
        except:
           print('RTI URL is not available, turning off --rti flag')
           rti = False

    try:
        while True:
            if event_handler.running == False:
                # Stop the DRP if 7am or later
                hourNow = int(dt.datetime.utcnow().strftime('%H'))
                if hourNow >= endHour:
                    print('Night is over - goodbye')
                    observer.stop()
                    return

                # Check the queue and process any files
                event_handler.process_current_file_list()

            sleep(30)
    except KeyboardInterrupt:
        observer.stop()

if __name__ == '__main__':
    main()
