'''
Data Evaluation and Processing
'''

import os
import sys
import importlib
import urllib.request
import ssl
import json
import numpy as np
import re
import math
import db_conn
import yaml
from astropy.io import fits
import datetime as dt
import shutil
import glob
import inspect
import fnmatch
import pathlib
import traceback
import subprocess
import pdb
from pathlib import Path
from pprint import pprint

import metadata
import update_koapi_send
from common import *
from envlog import *
import check_dep_status_errors

import logging
log = logging.getLogger('koa_dep')


class DEP:

    def __init__(self, instr, filepath, reprocess, transfer, progid, dbid=None):

        #class inputs
        self.instr     = instr.upper()
        self.filepath  = filepath
        self.reprocess = reprocess
        self.transfer  = transfer
        self.progid    = progid
        self.dbid      = dbid

        #init other vars
        self.koaid = ''
        self.fits_hdu = None
        self.fits_hdr = None
        self.extra_meta = {}
        self.errors = []
        self.warnings = []
        self.invalids = []
        self.stage_file = None
        self.ofname = None
        self.utdatedir = None
        self.utc = None
        self.utdate = None
        self.dirs = None
        self.rootdir = None
        self.config = None
        self.db = None
        self.filesize_mb = 0.0
        self.rtui = True

    def __del__(self):

        #Close the database connection
        if self.db:
            self.db.close()

    #abstract methods that must be implemented by inheriting classes
    def run_dqa(self) : raise NotImplementedError("Abstract method not implemented!")

    def process(self):
        '''Start processing based on level.'''
        # big catch for all unhandled exceptions
        try:
            ok = True
            if ok: ok = self.init()
            if ok: ok = self.create_logger()
            if ok: ok = self.get_level()
            if ok:
                if   self.level == 0: ok = self.process_lev0()
                elif self.level == 1: ok = self.process_lev1()
                elif self.level == 2: ok = self.process_lev2()
        except Exception as e:
            ok = False
            self.log_error('CODE_ERROR', traceback.format_exc())

        # handle any log_error, log_warn or log_invalid calls
        self.handle_dep_errors()
        return ok

    def process_lev0(self):
        '''Run all prcessing steps required for archiving lev0.'''

        funcs = [
            {'name': 'check_status_db_entry', 'crit': True},
            {'name': 'get_status_record',     'crit': True},
            {'name': 'init_processing',       'crit': True},
            {'name': 'determine_filepath',    'crit': True},
            {'name': 'load_fits',             'crit': True},
            {'name': 'set_koaid_by_level',    'crit': True},
            {'name': 'init_processing2',      'crit': True},
            {'name': 'check_koaid_db_entry',  'crit': True},
            {'name': 'cleanup_files',         'crit': True},
            {'name': 'change_logger',         'crit': True},
            {'name': 'validate_fits',         'crit': True},
            {'name': 'run_psfr',              'crit': True},
            {'name': 'run_dqa',               'crit': True},
            {'name': 'write_lev0_fits_file',  'crit': True},
            {'name': 'make_jpg',              'crit': False},
            {'name': 'set_filesize_mb',       'crit': False},
            {'name': 'create_meta',           'crit': True},
            {'name': 'create_ext_meta',       'crit': False},
            {'name': 'run_drp',               'crit': True},
            {'name': 'create_md5sum',         'crit': True},
            {'name': 'update_dep_stats',      'crit': True},
            {'name': 'add_header_to_db',      'crit': False},
            {'name': 'transfer_ipac',         'crit': True},
            {'name': 'check_koapi_send',      'crit': False},
            {'name': 'copy_raw_fits',         'crit': False},
            {'name': 'run_lev1',              'crit': True},
        ]
        return self.run_functions(funcs)

    def process_lev1(self):
        '''Run all prcessing steps required for archiving lev1.'''

        funcs = [
            {'name': 'get_status_record',    'crit': True},
            {'name': 'init_processing',      'crit': True},
            {'name': 'determine_filepath',   'crit': True},
            {'name': 'set_koaid_by_level',   'crit': True},
            {'name': 'init_processing2',     'crit': True},
            {'name': 'cleanup_files',        'crit': True},
            {'name': 'change_logger',        'crit': True},
            {'name': 'copy_drp_files',       'crit': True},
            {'name': 'run_lev1',             'crit': True},
            {'name': 'create_md5sum',        'crit': True},
            {'name': 'update_dep_stats',     'crit': True},
            {'name': 'transfer_ipac',        'crit': True},
        ]
        return self.run_functions(funcs)

    def process_lev2(self):
        '''Run all prcessing steps required for archiving lev2.'''

        funcs = [
            {'name': 'get_status_record',    'crit': True},
            {'name': 'init_processing',      'crit': True},
            {'name': 'determine_filepath',   'crit': True},
            {'name': 'set_koaid_by_level',   'crit': True},
            {'name': 'init_processing2',     'crit': True},
            {'name': 'cleanup_files',        'crit': True},
            {'name': 'change_logger',        'crit': True},
            {'name': 'copy_drp_files',       'crit': True},
            {'name': 'create_md5sum',        'crit': True},
            {'name': 'update_dep_stats',     'crit': True},
            {'name': 'transfer_ipac',        'crit': True},
        ]
        return self.run_functions(funcs)


    def run_functions(self, funcs):
        '''
        Run a list of functions by name.  If the function returns False or throws exception,
        check if it is a critical function before breaking processing.
        '''
        for f in funcs:
            name = f.get('name')
            crit = f.get('crit')
            args = f.get('args', {})
            log.info(f'Running process function: {name}')
            try: 
                ok = getattr(self, name)(**args)
            except Exception as e: 
                self.log_error('CODE_ERROR', traceback.format_exc())
                ok = False
            if not ok and crit:
                return False
        return True


    def init(self):
        # cd to script dir so relative paths work
        scriptpath = os.path.dirname(os.path.realpath(__file__))
        os.chdir(scriptpath)

        # load config file
        with open('config.live.ini') as f: 
            self.config = yaml.safe_load(f)

        # helpful vars from config
        try:
            self.rootdir = self.config[self.instr]['ROOTDIR']
            self.dev = self.config['RUNTIME']['DEV']
        except KeyError:
            print('ERROR on initialization.  \n'
                  'INST.ROOTDIR and RUNTIME.DEC must be defined in the'
                  ' configuration file')
            return False

        if self.rootdir.endswith('/'): self.rootdir = self.rootdir[:-1]

        # Establish database connection 
        self.db = db_conn.db_conn('config.live.ini', configKey='DATABASE',
                                  persist=True, log_obj=log)

        return True


    def create_logger(self):
        """
        Creates a logger based on rootdir, instr and cur date.
        NOTE: We create a temp log file first and once we have the KOAID,
        we will rename the logfile and change the filehandler
            (see dep.change_logger)
        """

        name = 'koa_dep'
        rootdir = self.config[self.instr]['ROOTDIR']
        instr = self.instr

        # Create logger object
        global log
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)

        #paths 
        processDir = f'{rootdir}/{instr.upper()}'
        ymd = dt.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        logFile =  f'{processDir}/logtmp/{name}_{instr.upper()}_{ymd}.log'

        #create directory if it does not exist
        try:
            Path(processDir).mkdir(parents=True, exist_ok=True)
            Path(os.path.dirname(logFile)).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"ERROR: Unable to create logger at {logFile}.  Error: {str(e)}")
            self.log_error('WRITE_ERROR')
            return False

        #Remove all handlers
        #NOTE: This is important if processing multiple files with archive.py since
        #we reuse global log object and do some renaming of log file (see change_logger())
        log.handlers = []

        # Create a file handler
        handle = logging.FileHandler(logFile)
        handle.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handle.setFormatter(formatter)
        log.addHandler(handle)

        #add stdout to output so we don't need both log and print statements(>= warning only)
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.WARNING)
        formatter = logging.Formatter('%(asctime)s %(levelname)s - %(message)s')
        sh.setFormatter(formatter)
        log.addHandler(sh)
        
        #init message and return
        log.info(f'logger created for {name} at {logFile}')
        print(f'Logging to {logFile}')
        return log


    def get_level(self):
        '''Determine processing level.  If filepath based (not from DB), assume lev 0.'''
        if not self.dbid: 
            self.level = 0
        else:
            res = self.get_status_record()
            if not res: return False
            self.level = self.status['level']
        return True


    def check_status_db_entry(self):
        '''
        If a filepath was passed in instead of a DB ID, we need to insert a new record
        and get that DB ID.
        '''

        #If we passed in a filepath and are reprocessing, look for existing record by ofname
        if self.filepath and self.reprocess:
            query = (f"select * from koa_status where level=0 and"
                     f" instrument='{self.instr}' and ofname='{self.filepath}' "
                      " order by id desc")
            log.info(query)
            row = self.db.query('koa', query, getOne=True)
            if row:
                self.dbid = row['id']

        #If we didn't pass in a DB ID, we must have filepath 
        #so insert a new koa_status record and get ID
        if not self.dbid:
            query = ("insert into koa_status set level=0, "
                    f"   instrument='{self.instr}' "
                    f" , ofname='{self.filepath}' "
                    f" , status='PROCESSING' "
                    f" , creation_time='{dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}' ")
            log.info(query)
            result = self.db.query('koa', query, getInsertId=True)
            if result is False: 
                self.log_error('QUERY_ERROR', query)
                return False
            self.dbid = result

        return True


    def get_status_record(self):
        '''
        Query for koa_status record by ID.  Typically we are given an id, but in
        in the case where ofname filepath passed in, we should still have a dbid by this point.
        '''
        query = f"select * from koa_status where id={self.dbid}"
        self.status = self.db.query('koa', query, getOne=True)
        if not self.status:
            self.log_error('DB_ID_NOT_FOUND', query)
            return False
        return True


    def init_processing(self):
        '''
        Perform initialization tasks for DEP processing.
        '''

        if self.reprocess: log.info(f"Reprocessing ID# {self.dbid}")
        else:              log.info(f"Processing ID# {self.dbid}")

        #if reprocessing, copy record to history and clear status columns
        if self.reprocess:
            self.copy_old_status_entry(self.dbid)
            self.reset_status_record(self.dbid)

        #update koa_status
        if not self.update_koa_status('status', 'PROCESSING'): return False
        if not self.update_koa_status('status_code', ''): return False
        if not self.update_koa_status('process_start_time', dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')): return False

        #handy list of files we will be transfering
        self.xfr_files = []

        return True


    def determine_filepath(self):
        '''Determine which filepath to use.  If stage file is defined and exists, use it.'''
        if self.level == 0:
            self.ofname     = self.status.get('ofname')
            self.stage_file = self.status.get('stage_file')
            self.filepath   = self.status.get('ofname')
            if self.stage_file and os.path.isfile(self.stage_file):
                self.filepath = self.stage_file
        else:
            #NOTE: We are not loading a fits file and updating certain koa_status cols for DRP
            self.filepath = None 
            pass
        log.info(f"Using fits filepath: {self.filepath}")
        return True


    def init_processing2(self):
        '''
        Perform more initialization tasks for DEP processing now that fits is loaded.
        '''

        #define some handy utdate vars here after loading fits (dependent on set_koaid())
        if self.level == 0:
            self.utdate = self.get_keyword('DATE-OBS', useMap=False)
            self.utdatedir = self.utdate.replace('/', '-').replace('-', '')
            hstdate = dt.datetime.strptime(self.utdate, '%Y-%m-%d') - dt.timedelta(days=1)
            self.hstdate = hstdate.strftime('%Y-%m-%d')
            self.utc = self.get_keyword('UTC', useMap=True)
            self.utdatetime = f"{self.utdate} {self.utc[0:8]}" 
            if not self.update_koa_status('utdatetime', self.utdatetime): return False
        else:
            self.utdatedir = self.status['koaid'].split('.')[1]
            self.utdate = self.utdatedir[0:4]+'-'+self.utdatedir[4:6]+'-'+self.utdatedir[6:8]
            self.utc = ''
            self.utdatetime = ''

        #create output dirs (this is dependent on utdatedir above)
        self.init_dirs()

        return True


    def check_koaid_db_entry(self):

        #Query for existing KOAID record
        service = self.status['service']
        query = (f"select * from koa_status "
                 f" where level={self.level} and koaid='{self.koaid}'"
                 f" and service='{service}'")
        rows = self.db.query('koa', query)
        if rows is False:
            self.log_error('QUERY_ERROR', query)
            return False

        #If entry exists and we are not reprocessing, return error
        if len(rows) > 0 and not self.reprocess:
#            self.log_invalid('DUPLICATE_KOAID')
            self.log_warn('DUPLICATE_KOAID', "KOAID already exists.")
            return False

        #Now that KOAID check is passed, update koa_status.koaid
        if not self.update_koa_status('koaid', self.koaid): return False

        return True


    def cleanup_files(self):
        #if reprocessing, delete old local files by KOAID
        if self.reprocess:
            self.delete_local_files(self.instr, self.koaid)
        return True


    def init_dirs(self):

        # get the various root dirs
        self.set_root_dirs()

        # Create the output directories, if they don't already exist.
        for key, dir in self.dirs.items():
            if not os.path.isdir(dir):
                log.info(f'Creating output directory: {dir}')
                try:
                    pathlib.Path(dir).mkdir(parents=True, exist_ok=True)
                except:
                    raise Exception(f'instrument.py: could not create directory: {dir}')

        #store levN outdir since we need this a lot
        self.levdir = self.dirs[f'lev{self.level}']


    def set_root_dirs(self):
        """Sets the various rootdir subdirectories of interest"""

        rootdir = self.rootdir
        instr = self.instr
        ymd = self.utdatedir

        self.dirs = {}
        self.dirs['process'] = f"{rootdir}/{instr}"
        self.dirs['output']  = f"{rootdir}/{instr}/{ymd}"
        self.dirs['lev0']    = f"{rootdir}/{instr}/{ymd}/lev0"
        self.dirs['lev1']    = f"{rootdir}/{instr}/{ymd}/lev1"
        self.dirs['lev2']    = f"{rootdir}/{instr}/{ymd}/lev2"
        self.dirs['stage']   = f"{rootdir}/{instr}/stage"
        self.dirs['udf']     = f"{rootdir}/{instr}/stage/udf"


    def change_logger(self):

        '''Now that we have a KOAID, change fileHandler logger.'''

        #Find logger and FileHandler 
        #NOTE: monitor.py has its own logger which will be in loggerDict
        fileHandler = None
        logger = None
        for k, l in  logging.Logger.manager.loggerDict.items():
            if isinstance(l, logging.PlaceHolder): continue
            for h in l.handlers:
                if 'FileHandler' not in str(h.__class__): continue
                if 'koa_dep' not in h.baseFilename: continue
                fileHandler = h
                logger = l
                break

        if not fileHandler:
            self.log_error('CHANGE_LOGGER_ERROR')
            return False

        #rename
        lev = f'lev{self.level}'
#        if self.level in (0,1):
        newfile = f"{self.dirs[lev]}/{self.koaid}.log"
#        else:
#            newfile = f"{self.dirs[lev]}/dep_{lev}_{self.utdatedir}.log"
        print(f"Logger renamed to {newfile}")
        log.info(f"Renaming log file from {fileHandler.baseFilename} to {newfile}")
        shutil.move(fileHandler.baseFilename, newfile)

        #remove old fileHandler and add new
        logger.removeHandler(fileHandler)

        handle = logging.FileHandler(newfile, mode='a')
        handle.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handle.setFormatter(formatter)
        logger.addHandler(handle)

        return True


    def set_koaid_by_level(self):
        '''
        If processing raw fits file, we need to call some complicated code to get koaid.
        Otherwise, we can just use what is in DB.
        '''
        if self.level == 0:
            return self.set_koaid()
        else:
            self.koaid = self.status['koaid']
            return True


    def load_fits(self):
        '''
        Loads the fits file
        '''
        #If mount is broken/hung, isfile() hangs indefinitely, so we first do 
        #a check_call to make catch mount issues
        try:
            subprocess.check_call(['test', '-f', self.filepath], timeout=5)
        except Exception as e:
            self.log_error('FITS_FILE_TYPE_ERROR', str(e))
            if os.path.isfile(self.filepath):
                log.error('Got a FITS_FILE_TYPE_ERROR, but os.path.isfile is OK.')
            else:
                self.log_error('FITS_NOT_FOUND', self.filepath)
            return False

        #check file not found and file empty
        if not os.path.isfile(self.filepath):
            self.log_error('FITS_NOT_FOUND', self.filepath)
            return False
        if (os.path.getsize(self.filepath) == 0):
            self.log_invalid('EMPTY_FILE')
            return False

        #fits load
        try:
            self.fits_hdu = fits.open(self.filepath, ignore_missing_end=True)
            self.fits_hdr = self.fits_hdu[0].header
        except:
            self.log_invalid('UNREADABLE_FITS')
            return False
        return True


    def copy_old_status_entry(self, id):

        #move to history table 
        query = (f"INSERT INTO koa_status_history "
                f" SELECT ds.* FROM koa_status as ds " 
                f" WHERE id = {id}")
        log.info(query)
        result = self.db.query('koa', query)
        if result is False: 
            self.log_error('QUERY_ERROR', query)
            return False
        return True


    def reset_status_record(self, id):
        '''When reprocessing a record, we need to reset most columns to default.'''
        query = (f"update koa_status set "
                 f" status_code        = NULL, " 
                 f" status_code_ipac   = NULL, " 
                 f" process_dir        = NULL, "
                 f" archive_dir        = NULL, "
                 f" creation_time='{dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}', "
                 f" process_start_time = NULL, "
                 f" process_end_time   = NULL, "
                 f" xfr_start_time     = NULL, "
                 f" xfr_end_time       = NULL, "
                 f" ipac_notify_time   = NULL, "
                 f" ipac_response_time = NULL, "
                 f" stage_time         = NULL, "
                 f" filesize_mb        = NULL, "
                 f" archsize_mb        = NULL, "
                 f" koaimtyp           = NULL, "
                 f" semid              = NULL "
                 f" where id = {id} ")
        log.info(query)
        result = self.db.query('koa', query)
        if result is False: 
            self.log_error('QUERY_ERROR', query)
            return False
        return True


    def copy_raw_fits(self, invalid=False):
        '''
        Copy raw fits file so we have a copy at Keck before summit disks get wiped.
        NOTE: Stage is sort of a misnomer here since we are doing this at the end
        of processing and we don't use it except for reprocessing.  But since
        the copy can take a while, we do it at the end after ipac transfer.
        NOTE: We could move this just after processing_init() if we don't care about delay.
        '''

        #if record already has stage_file defined and it exists, no copy needed
        if self.stage_file and os.path.isfile(self.stage_file):
            log.info('Stage file defined and exists.  No copy needed.')
            return True        

        if invalid and not self.ofname:
            log.info('No raw fits file to copy.')
            return True

        #form filepath and copy
        if invalid: 
            #NOTE: We decided to not make udf copies of invalid files.
            return True
            # if self.dirs: outfile = f"{self.dirs['udf']}/{self.utdatedir}/{self.ofname}"
            # else:         outfile = f"{self.rootdir}/{self.instr}/stage/udf/{self.ofname}"
        else:       
            outfile = f"{self.dirs['stage']}/{self.utdatedir}/{self.ofname}"
        if outfile == self.filepath:
            return True

        #if outfile exists, we append version to filename
        #(This is for rare case where observer deletes file and recreates it)
        if os.path.isfile(outfile):
            log.warning(f'Stage file already exists.  Renaming with version.')
            outdir = os.path.dirname(outfile)
            base = os.path.basename(outfile)
            for i in range(2,20):
                idx = base.rfind('.')
                if idx >= 0: newbase = f"{base[:idx]}_ver{i}{base[idx:]}"
                else:        newbase = f"{base}_ver{i}"
                outfile = f"{outdir}/{newbase}"
                if not os.path.isfile(outfile):
                    break

        #copy file
        log.info(f'Copying raw fits to {outfile}')
        try:
            outdir = os.path.dirname(outfile)
            pathlib.Path(outdir).mkdir(parents=True, exist_ok=True)
            shutil.copy(self.filepath, outfile)  
        except Exception as e:
            self.log_error('FILE_COPY_ERROR', outfile)
            return False
      
        #update koa_status.savepath
        self.update_koa_status('stage_file', outfile)
        return True


    def get_raw_filepath(self):
        filename = os.path.basename(self.filepath)
        outdir = self.dirs['output']
        outdir = outdir.replace(self.rootdir, '')
        outfile = f"{self.config[self.instr]['ROOTDIR']}{outdir}/{filename}"
        return outfile


    def delete_local_files(self, instr, koaid):
        '''
        Delete local archived output files.  
        This is important if we are reprocessing data.
        '''

#todo: get this working for levN
        if self.level > 0:
            return True

        if not self.koaid or len(self.koaid) < 20:
            self.log_error('INVALID_KOAID')
            return False

        #delete files matching KOAID*
        try:
            log.info(f'Deleting local files in {self.levdir}')
            for path in Path(self.levdir).rglob(f'*{self.koaid}*'):
                path = str(path)
                if "_unp" in path and "_unp" not in self.koaid:
                    continue
                log.info(f"removing file: {path}")
                os.remove(path)
        except Exception as e:
            self.log_error('FILE_DELETE_ERROR', self.levdir)
            return False
        return True


    def update_koa_status(self, column, value):
        """Sends command to update KOA koa_status."""

        if value is None: query = f"update koa_status set {column}=NULL where id='{self.dbid}'"
        else:             query = f"update koa_status set {column}='{value}' where id='{self.dbid}'"
        log.info(query)
        result = self.db.query('koa', query)
        if result is False:
            self.log_error('QUERY_ERROR', query)
            return False
        return True


    def validate_fits(self):
        '''Basic checks for valid FITS before proceeding with archiving'''

        # check no data
        if len(self.fits_hdu) == 0:
            self.log_invalid('NO_FITS_HDUS')
            return False

        # any corrupted HDUs?
        for hdu in self.fits_hdu:
            hdu_type = str(type(hdu))
            if 'CorruptedHDU' in hdu_type:
                self.log_invalid('CORRUPTED_HDU')
                return False

        # certain text in filepath is indication that it should not be archived.
        # TODO: review this logic with Jeff
        rejects = ['mira', 'savier-protected', 'SPEC/ORP', '/subtracted', 'idf']
        for reject in rejects:
            if reject in self.filepath:
                self.log_invalid('FILEPATH_REJECT')
                return False

        # Construct the original file name
        res = self.set_ofName()
        if res is False:
            self.log_invalid('BAD_OFNAME')
            return False
        filename = self.get_keyword('OFNAME', False)

        # Make sure constructed filename matches basename.
        basename = os.path.basename(self.filepath)
        basename = basename.replace(".fits.gz", ".fits")
        if filename != basename:
            self.log_invalid('MISMATCHED_FILENAME', f"{filename} != {basename}")
            return False

        return True


    def create_meta(self):
        extra_meta = {}
        koaid = self.get_keyword('KOAID')
        extra_meta[koaid] = self.extra_meta
        extra_meta[koaid]['FILESIZE_MB'] = self.filesize_mb
        extra_meta[koaid]['SEMID'] = self.get_semid()
        propint = extra_meta[koaid]['PROPINT']
        if propint != 18:
            self.update_koa_status('propint', propint)

        keydefs = f"{self.config['MISC']['METADATA_TABLES_DIR']}/KOA_{self.instr}_Keyword_Table.txt"
        metaoutfile =  self.levdir + '/' + self.koaid + '.metadata.table'
        md = metadata.Metadata(keydefs, metaoutfile, fitsfile=self.outfile, 
                               extraMeta=extra_meta, keyskips=self.keyskips,
                               dev=self.dev)
        try:      
            warns = md.make_metadata()
        except Exception as err:
            self.log_error('METADATA_ERROR', str(err))
            return False
        else:
            for warn in warns:
                    self.log_warn(warn['code'], warn['msg'])
            return True


    def create_ext_meta(self):
        '''
        Creates IPAC ASCII formatted data files for any extended header data found.
        '''
        #todo: put in warnings for empty ext headers

        #read extensions and write to file
        filename = os.path.basename(self.outfile)
        for i in range(0, len(self.fits_hdu)):
            #wrap in try since some ext headers have been found to be corrupted
            try:
                hdu = self.fits_hdu[i]
                if 'TableHDU' not in str(type(hdu)) or not hdu.name:
                    continue

                #calc col widths
                dataStr = ''
                colWidths = []
                for idx, colName in enumerate(hdu.data.columns.names):
                    if hdu.data.formats[idx][1:].isdigit():
                        fmtWidth = int(hdu.data.formats[idx][1:])
                    elif hdu.data.formats[idx][:-1].isdigit():
                        fmtWidth = int(hdu.data.formats[idx][:-1])
                    else:
                        fmtWidth = 24

                    if fmtWidth < 16:
                        fmtWidth = 16

                    colWidth = max(fmtWidth, len(colName))
                    colWidths.append(colWidth)

                #add hdu name as comment
                dataStr += r'\ Extended Header Name: ' + hdu.name + "\n"

                #add header
                #NOTE: Found that all ext data is stored as strings regardless of type 
                #it seems, so hardcoding to 'char' for now.
                for idx, cw in enumerate(colWidths):
                    dataStr += '|' + hdu.data.columns.names[idx].ljust(cw)
                dataStr += "|\n"
                for idx, cw in enumerate(colWidths):
                    dataStr += '|' + 'char'.ljust(cw)
                dataStr += "|\n"
                for idx, cw in enumerate(colWidths):
                    dataStr += '|' + ''.ljust(cw)
                dataStr += "|\n"
                for idx, cw in enumerate(colWidths):
                    dataStr += '|' + ''.ljust(cw)
                dataStr += "|\n"

                #add data rows
                for j in range(0, len(hdu.data)):
                    row = hdu.data[j]
                    for idx, cw in enumerate(colWidths):
                        valStr = row[idx]
                        dataStr += ' ' + str(valStr).ljust(cw)
                    dataStr += "\n"

                #write to outfile
                outDir = os.path.dirname(self.outfile)
                outFile = filename.replace('.fits', '.ext' + str(i) + '.' + hdu.name.replace(' ', '_') + '.tbl')
                outFilepath = f"{outDir}/{outFile}"
                log.info('Creating {}'.format(outFilepath))
                with open(outFilepath, 'w') as f:
                    f.write(dataStr)

            except Exception as e:
                self.log_warn('EXT_HEADER_FILE_ERROR', str(e))
                log.error(str(e))
                return False

        return True


    def copy_drp_files(self):
        '''
        Copy all DRP files that will be archived to levN dir.
        Store dict of files by koaid in self.drp_files for later use.
        '''

        # Skip if this entry is not for a DRP
        if self.status['service'] != 'DRP':
            return True

        # get list of koaids we are dealing with (lev1 is just one koaid)
        datadir = self.status['stage_file']
        koaids = [self.status['koaid']]

        # For each koaid, get associated drp files and copy them to outdir.
        # Keep dict of files by koaid.
        self.drp_files = {}
        for koaid in koaids:
            files = self.get_drp_files_list(datadir, koaid, self.level)
            if files == False:
                self.log_error('FILE_NOT_FOUND', f"{koaid} level {self.level}")
                return False
            for srcfile in files:
                if not os.path.isfile(srcfile): continue
                try:
                    status, destfile = self.get_drp_destfile(koaid, srcfile)
                    if status == False:
                        split = srcfile.split('/')
                        outdir = self.dirs[f'lev{self.level}']
                        if split[-2] in ['plots','redux','logs']:
                            outdir = f'{outdir}/{split[-2]}'
                        destfile = f"{outdir}/{os.path.basename(srcfile)}"
                    log.info(f"Copying {srcfile} to {destfile}")
                    os.makedirs(os.path.dirname(destfile), exist_ok=True)
                    # Don't recopy files that haven't been updated
                    skip = False
                    if os.path.exists(destfile):
                        modTime1 = os.path.getmtime(srcfile)
                        modTime2 = os.path.getmtime(destfile)
                        if modTime1 > modTime2: skip = True
                    if skip == False:
                        subprocess.call(['rsync', '-az', srcfile, destfile])

                    if koaid not in self.drp_files: self.drp_files[koaid] = []
                    self.drp_files[koaid].append(destfile)
                    self.xfr_files.append(destfile)
                except Exception as e:
                    self.log_error('FILE_COPY_ERROR', f"{srcfile} to {destfile}")
                    return False

        return True
      

    def run_lev1(self):
        '''Run an RTI version of level 1 processing, defined in instr_*.py.'''
        return True


    def get_unique_koaids_in_dir(self, datadir):
        '''
        Get a list of unique koaids by looking at all filenames in directory 
        and regex matching a KOAID pattern.
        '''
        koaids = []
        for path in Path(datadir).rglob('*'):
            path = str(path)
            fname = os.path.basename(path)
            match = re.search(r'^(\D{2}\.\d{8}\.\d{5}\.\d{2})', fname)
            if not match: continue
            koaids.append(match.groups(1)[0])
        koaids = list(set(koaids))
        return koaids


    def create_md5sum(self):
        '''Create ext.md5sum.table for all files matching KOAID*'''

        try:
            outdir = self.dirs[f'lev{self.level}']
            if self.level == 0:
                md5Outfile = f'{outdir}/{self.koaid}.md5sum.table'
                log.info(f'Creating {md5Outfile}')
                # Now that KOAID can have _[value], need the ending .
#                kid = f'{self.koaid}\.'
                kid = f'{self.koaid}'
                make_dir_md5_table(outdir, None, md5Outfile, regex=kid, koaid=self.koaid)
                self.xfr_files.append(md5Outfile)                
            elif self.level in (1, 2):
                for koaid, files in self.drp_files.items():
                    md5Outfile = f'{outdir}/{koaid}.md5sum.table'
                    log.info(f'Creating {md5Outfile}')
                    make_dir_md5_table(outdir, None, md5Outfile, fileList=files)
                    self.xfr_files.append(md5Outfile)                
            return True
        except Exception as e:
            self.log_error('CREATE_MD5_SUM_ERROR', str(e))
            return False


    def get_drp_files_list(self, datadir, koaid, level):
        '''Return list of files to archive for DRP specific to instrument.'''
        raise NotImplementedError("Abstract method not implemented!")

    def get_drp_destfile(self, koaid, srcfile):
        '''Return output destination file to copy DRP file to.'''
        # Use default from copy_drp_files() - backwards compatibility with KCWI
        return False, ''

    def check_koapi_send(self):
        '''
        For each unique semids processed in DQA, call function that determines
        whether to flag semids for needing an email sent to PI that there data is archived
        '''

        #check if we should update koapi_send
        semid = self.get_semid()
        if not semid:
            self.log_warn('CHECK_KOAPI_SEND_ERROR', "No SEMID defined.")
            return False

        try:
            _, prog = semid.upper().split('_')
        except ValueError:
            self.log_warn('CHECK_KOAPI_SEND_ERROR', "Incorrect format for SEMID")
            return False

        if prog == 'NONE' or prog == 'NULL' or prog == 'ENG':
            return True

        #process it
        log.info(f'check_koapi_send: {self.utdate}, {semid}, {self.instr}')
        try:
            update_koapi_send.update_koapi_send(self.utdate, semid, self.instr)
        except Exception as e:
            self.log_warn('CHECK_KOAPI_SEND_ERROR', f"{self.utdate}, {semid}, {self.instr}")
            return False

        #NOTE: This should not hold up archiving
        return True


    def handle_dep_errors(self):
        '''
        Errors are serious and will set the koa_status.status to "ERROR" and will
        call the check_dep_status_errors email script.
        Warnings are less serious and will only set koa_status.status_code and will
        not call the check_dep_status_errors email script.
        Invalids are those errors that we know can be fully ignored.
        '''

        #if not errors or warnings, return
        if not self.invalids and not self.errors and not self.warnings:
            log.info("No DEP errors or warnings")
            return

        #If errors, those will trump any warnings
        if   self.invalids: data = self.invalids[-1]
        elif self.errors:   data = self.errors[-1]
        elif self.warnings: data = self.warnings[-1]
        status  = data['status']
        errcode = data['errcode']
        log.warning(f"Found {len(self.errors)} errors and {len(self.warnings)} warnings.")

        #update by dbid
        #NOTE: WARN only status does not change koa_status.status
        if self.dbid:
            query =  f"update koa_status set status_code='{errcode}' "
            if status != 'WARN': query += f", status='{status}' "
            query += f" where id={self.dbid}"
            log.info(query)
            result = self.db.query('koa', query)
            if result is False: 
                log.error(f'STATUS QUERY FAILED: {query}')
                return False

        #Copy to anc if INVALID
        if status == 'INVALID':
            self.copy_raw_fits(invalid=True)

        #call check_dep_status_errors
        if (status == 'ERROR' or status == 'WARN') and not self.dev:
            check_dep_status_errors.main(dev=self.dev, admin_email=self.config['REPORT']['ADMIN_EMAIL'], slack=True)


    def verify_utc(self, utc=''):
        """
        Verify that utc value has the format hh:mm:ss[.ss]
        hh between 0 and 24
        mm between 0 and 60
        ss between 0 and 60
        """        
        # Verify correct format (hh:mm:ss[.ss])
        if not utc: return False
        if not re.search(r'\d\d:\d\d:\d\d', utc): return False
        
        # Check time components       
        hour, minute, second = utc.split(':')        
        if int(hour) < 0 or int(hour) > 24: return False
        if int(minute) < 0 or int(minute) > 60: return False
        if float(second) < 0 or float(second) > 60: return False

        return True


    def is_progid_valid(self, progid):
        '''
        Check if progid is valid.
        NOTE: We allow the old style of progid without semester thru this check.
        '''
        if not progid or progid == 'NONE': return False

        #get valid parts
        if   progid.count('_') > 1 : return False    
        elif progid.count('_') == 1: sem, progid = progid.split('_')
        else                       : sem = False

        #checks
        if len(progid) <= 2:      return False
        if len(progid) >= 6:      return False
        if " " in progid:         return False
        if "PROGID" in progid:    return False
        if sem and len(sem) != 5: return False

        return True


    def get_prog_inst(self, semid, default=None, isToO=False):
        '''Query for the program institution'''
        api = self.config.get('API', {}).get('MAIN')
        url = api + '/proposals/getAllocInst?ktn='+semid
        data = self.get_api_data(url)
        if not data or not data.get('success'):
            self.log_warn('PROP_API_ERROR', url)
            return default
        else:
            val = data.get('data', {}).get('AllocInst', default)
            return val.replace(' ', '')


    def get_prog_pi(self, semid, default=None):
        '''Query for program's PI last name'''

        api = self.config.get('API', {}).get('MAIN')
        url = api + '/proposals/getPI?ktn='+semid
        data = self.get_api_data(url)
        if not data or not data.get('success'):
            self.log_warn('PROP_API_ERROR', url)
            return default
        else:
            val = data.get('data', {}).get('LastName', default)
            val = val.replace(' ', '')
            return val


    def get_prog_title(self, semid, default=None):
        '''Query the DB and get the program title'''
        api = self.config.get('API', {}).get('MAIN')
        url = api + '/proposals/getTitle?ktn='+semid
        data = self.get_api_data(url)
        if not data or not data.get('success'):
            self.log_warn('PROP_API_ERROR', url)
            return default
        else:
            val = data.get('data', {}).get('ProgramTitle', default)
            return val


    def update_dep_stats(self):
        '''Record DEP stats before we xfr to ipac.'''

        if self.level == 0:
            semid = self.get_semid()
            if not self.update_koa_status('semid', semid): return False

            koaimtyp = self.get_keyword('KOAIMTYP')
            if not self.update_koa_status('koaimtyp', koaimtyp): return False

        if not self.update_koa_status('process_dir', self.levdir): return False

        if not self.update_koa_status('filesize_mb', self.filesize_mb): return False

        archsize_mb = self.get_archsize_mb()
        if not self.update_koa_status('archsize_mb', archsize_mb): return False

        now = dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        if not self.update_koa_status('process_end_time', now): return False

        return True


    def set_filesize_mb(self):
        """Returns the archived fits size in MB"""
        bytes = os.path.getsize(self.outfile)
        self.filesize_mb = round(bytes/1e6, 4)


    def get_archsize_mb(self):
        """Returns the archive size in MB"""
        bytes = 0
        if self.level == 0:
            files = self.get_koaid_files()
        else:
            files = self.drp_files[self.koaid]
        for path in files:
            bytes += os.path.getsize(path)
        return str(bytes/1e6)


    def get_koaid_files(self):
        '''Recursive search for all files with KOAID in filename.'''
        search = f"{self.levdir}/{self.koaid}*"
        files = []
        for path in Path(self.levdir).rglob(f'*{self.koaid}*'):
            path = str(path)
            if f"{self.koaid}.log" in path:
                continue
            if "_unp" in path and "_unp" not in self.koaid:
                continue
            files.append(path)
        return files


    def get_api_data(self, url, getOne=False, isJson=True):
        '''
        Gets data for common calls to url API requests.
        '''
        log.info(f'Getting data from {url}')
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            data = urlopen(url, context=ctx)
            data = data.read().decode('utf8')
            if isJson: data = json.loads(data)
            if getOne and len(data) > 0: 
                data = data[0]
            return data
        except Exception as e:
            log.warn(f'API call failed: {url}')
            log.warn(str(e))
            return None


    def transfer_ipac(self):
        """
        Transfers the data set for koaid located in the output directory to its
        final archive destination.  After successful transfer of data set, 
        ingestion API (KOAXFR:INGESTAPI) is called to trigger the archiving process.
        """

        # Add the file to odap_queue
#        if self.level in [0, 1]:
#            try:
#                if not any(odap in self.koaid for odap in self.config["MISC"]["ODAP_SKIP"]):
#                    thisfile = f"{self.levdir}/{self.koaid}.fits"
#                    query = (f"insert into odap_queue set filename='{thisfile}', \
#                               level={self.level}, koaid='{self.koaid}'")
#                    print(query)
#                    result = self.db.query('koa', query)
#            except:
#                print(f"Unable to add {self.filepath} to odap_queue")

        if not self.transfer:
            log.warning('NOT TRANSFERRING TO IPAC.  Use --transfer flag or add'
                        'transfer to monitor_config.py if using monitor.py.')
            return True

        # shorthand vars
        fromDir = self.levdir

        # Verify that this dataset should be transferred
        query = f'select * from koa_status where id={self.dbid} and xfr_start_time is null'
        row = self.db.query('koa', query, getOne=True)
        if not row:
            self.log_error('TRANSFER_BAD_STATUS')
            return False

        # Verify that there is a dataset to transfer
        if not os.path.isdir(fromDir):
            self.log_error('NO_TRANSFER_DIR', fromDir)
            return False

        #get file list to send
        if self.level == 0:
            koaid_files = self.get_koaid_files()
            self.xfr_files += koaid_files
        self.xfr_files = list(set(self.xfr_files))
        if len(self.xfr_files) == 0:
            self.log_error('NO_TRANSFER_FILES', fromDir)
            return False

        #make sure all files exist
        for file in self.xfr_files:
            if not os.path.isfile(file):
                self.log_error('TRANSFER_FILE_MISSING', file)
                return False

        # xfr config parameters
        server = self.config['KOAXFR']['SERVER']
        account = self.config['KOAXFR']['ACCOUNT']
        toDir = self.config['KOAXFR']['DIR']
        api = self.config['KOAXFR']['INGESTAPI']

        # Configure the transfer command
        utstring = dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        if not self.update_koa_status('xfr_start_time', utstring): return False
        if not self.update_koa_status('status', 'TRANSFERRING'): return False

        toLocation = f'{account}@{server}:{toDir}/{self.instr}/{self.utdatedir}/lev{self.level}/'
        log.info(f'transferring directory {fromDir} to {toLocation}')

        if self.level == 2 and self.instr == 'KCWI':
            xfrOutfile = f'{self.levdir}/{self.utdatedir}.xfr.table'
        else:
            xfrOutfile = f'{self.levdir}/{self.koaid}.xfr.table'
        with open(xfrOutfile, 'w') as fp:
            for srcfile in self.xfr_files:
                file = srcfile.replace(f'{self.levdir}/', '')
                fp.write(f'{file}\n')
        stageDir = f'{toDir}/{self.instr}/{self.utdatedir}/lev{self.level}/'
        cmd = f'ssh {account}@{server} mkdir -p {stageDir}'
        log.info(cmd)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output, error = proc.communicate()
        cmd = f'rsync -avzR --no-t --compress-level=1 --files-from={xfrOutfile} {fromDir} {toLocation}'
        log.info(cmd)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output, error = proc.communicate()
        if error:
            self.update_koa_status('xfr_start_time', None)
            self.log_error('TRANSFER_ERROR', error)
            return False

        # Transfer success
        utstring = dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        if not self.update_koa_status('xfr_end_time', utstring): return False
        if not self.update_koa_status('status', 'TRANSFERRED'): return False

        # Send API request to archive the data set
        if not api and not self.dev:
            self.log_error('IPAC_API_UNDEFINED')
            return False
        else:
            # Do not trigger ingestion for individual lev2 data products
            # Only trigger if all koa_status entries are COMPLETE
            if self.level == 2:
                # This will be removed when we move to individual KOAID ingests
                if self.instr == 'KCWI':
                    # Only continue to ingestion API if all KOAIDs have been processed
                    query = f"select * from koa_status where instrument='{self.instr}' and koaid like '%{self.utdatedir}%' and level=2"
                    result = self.db.query('koa', query)
                    notDone = [i for i in result if i['status'] != 'TRANSFERRED']
                    if len(notDone) == 0:
                        print(f"All data processed, triggering ingestion")
                        log.info(f"All data processed, triggering ingestion")
                    else:
                        print(f"{len(notDone)} of {len(result)} still to process")
                        log.info(f"{len(notDone)} of {len(result)} still to process")
                        return True

            apiUrl = f'{api}instrument={self.instr}&ingesttype=lev{self.level}'
            if self.level in (0,1):
                apiUrl = f'{apiUrl}&koaid={self.koaid}'
            else:
                # Will be removed
                if self.instr == 'KCWI':
                    apiUrl = f'{apiUrl}&utdate={self.utdatedir}'
                else:
                    apiUrl = f'{apiUrl}&koaid={self.koaid}'
            if self.reprocess:
                apiUrl = f'{apiUrl}&reingest=true'
            if not self.rtui:
                apiUrl = f'{apiUrl}&rtui=false'


            log.info(f'sending ingest API call {apiUrl}')
            utstring = dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            if not self.update_koa_status('ipac_notify_time', utstring): return False
            apiData = self.get_api_data(apiUrl)
            log.info(f"IPAC API response: {apiData}")
            if not apiData or not apiData.get('APIStatus') or apiData.get('APIStatus') != 'COMPLETE':
                self.log_error('IPAC_NOTIFY_ERROR', apiUrl)
                return False

        return True

    def add_header_to_db(self):
        '''
        Converts the primary header into a dictionary and inserts that 
        data into the json column of the headers database table.
        '''
        d = {}
        for key in self.fits_hdr.keys():
            if key == 'COMMENT' or key == '' or key in d.keys():
                continue
            d[key] = {}
            d[key]['value'] = self.get_keyword(key)
            d[key]['comment'] = self.fits_hdr.comments[key]

        query = 'insert into headers set koaid=%s, header=%s'
        vals = (self.koaid, json.dumps(d),)

        if self.reprocess:
            # check to see if the value is the headers table.
            query_chk = 'select koaid from headers where koaid=%s'
            result = self.db.query('koa', query_chk, values=(self.koaid,))

            if result:
                query = 'update headers set header=%s where koaid=%s'
                vals = (json.dumps(d), self.koaid,)

        result = self.db.query('koa', query, values=vals)

        if not result:
            self.log_warn('HEADER_TABLE_INSERT_FAIL', query)
            return False

        return True


    def log_warn(self, errcode, text=''):
        status = 'WARN'
        caller = inspect.stack()[1][3]
        data = {'func': caller, 'status': status, 'errcode':errcode, 'text':text}
        log.warning(f"func: {caller}, db id: {self.dbid}, koaid: {self.koaid}, status: {status}, errcode:{errcode}, text:{text}")
        self.warnings.append(data)

    def log_error(self, errcode, text=''):
        status = 'ERROR'
        caller = inspect.stack()[1][3]
        data = {'func': caller, 'status': status, 'errcode':errcode, 'text':text}
        log.error(f"func: {caller}, db id: {self.dbid}, koaid: {self.koaid}, status: {status}, errcode:{errcode}, text:{text}")
        self.errors.append(data)

    def log_invalid(self, errcode, text=''):
        status = 'INVALID'
        caller = inspect.stack()[1][3]
        data = {'func': caller, 'status': status, 'errcode':errcode, 'text':text}
        log.error(f"func: {caller}, db id: {self.dbid}, koaid: {self.koaid}, status: {status}, errcode:{errcode}, text:{text}")
        self.invalids.append(data)

