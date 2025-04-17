
CREATE TABLE IF NOT EXISTS `koa_status` (
  `id`                     int(11)       NOT NULL  AUTO_INCREMENT PRIMARY KEY,
  `level`                  int(11)                     COMMENT 'Data processing level',
  `koaid`                  varchar(48)                 COMMENT 'Unique KOA ID',
  `instrument`             varchar(15)   NOT NULL      COMMENT 'Instrument name',
  `service`                varchar(16)                 COMMENT 'Instrument KTL service',
  `utdatetime`             datetime                    COMMENT 'DATE-OBS UTC',
  `status`                 varchar(15)                 COMMENT 'Current status of archive process [QUEUED, PROCESSING, COMPLETE, INVALID, ERROR]',
  `status_code`            varchar(30)                 COMMENT 'Status code of archive process [NULL, DUPLICATE, EMPTY, UNREADABLE, etc]',
  `status_code_ipac`       varchar(30)                 COMMENT 'Status code of ingestion process',
  `ofname`                 varchar(255)                COMMENT 'Full path to original file (sdata location)',
  `stage_file`             varchar(255)                COMMENT 'Full path the staged original raw file',
  `process_dir`            varchar(255)                COMMENT 'Directory output files are processed',
  `archive_dir`            varchar(255)                COMMENT 'Directory file is archived',
  `creation_time`          datetime                    COMMENT 'Date and time the FITS file is ready to be processed',
  `process_start_time`     datetime                    COMMENT 'Date and time that DEP processing started',
  `process_end_time`       datetime                    COMMENT 'Date and time that file processing is complete',
  `xfr_start_time`         datetime                    COMMENT 'Date and time that transfer started',
  `xfr_end_time`           datetime                    COMMENT 'Date and time that transfer is complete',
  `ipac_notify_time`       datetime                    COMMENT 'Date and time that IPAC is notified to start ingestion',
  `ingest_start_time`      datetime                    COMMENT 'Date and time that IPAC ingestion started',
  `ingest_copy_start_time` datetime                    COMMENT 'Date and time that IPAC transfer started',
  `ingest_copy_end_time`   datetime                    COMMENT 'Date and time that IPAC transfer is complete',
  `ingest_end_time`        datetime                    COMMENT 'Date and time that IPAC ingestion is complete',
  `ipac_response_time`     datetime                    COMMENT 'Date and time that IPAC ingestion response received',
  `stage_time`             datetime                    COMMENT 'Date and time that original file copied to stage directory',
  `filesize_mb`            double                      COMMENT 'FITS file size in megabytes',
  `archsize_mb`            double                      COMMENT 'Size of complete FITS dataset in megabytes',
  `koaimtyp`               varchar(25)                 COMMENT 'Image type of the FITS file',
  `semid`                  varchar(25)                 COMMENT 'SEMID of FITS file association',
  `propint`                integer                     COMMENT 'Proprietary period for FITS file',
  `source_deleted`         tinyint(1)                  COMMENT '0 file not deleted, 1 file deleted, 2 do not delete file.',
  `last_mod`               timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE `uidx` (`level`,`koaid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;

CREATE TABLE `koa_status_history` like `koa_status`;
ALTER TABLE  `koa_status_history` drop index `uidx`;
ALTER TABLE  `koa_status_history` DROP PRIMARY KEY, CHANGE id id int(11);


CREATE TABLE IF NOT EXISTS `headers` (
  `koaid`         varchar(48)   PRIMARY KEY         COMMENT 'Unique KOA ID',
  `header`        json          DEFAULT NULL        COMMENT 'Store all FITS header info as json',    
  `last_mod`      timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;


CREATE TABLE IF NOT EXISTS `dep_error_notify` (
  `id`            int(11)       NOT NULL  AUTO_INCREMENT PRIMARY KEY,
  `instr`         varchar(15)   DEFAULT NULL            COMMENT 'Instrument name',
  `email_time`    datetime      DEFAULT NULL        COMMENT 'Time last admin error email sent for this instrument.'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;


CREATE TABLE IF NOT EXISTS `koa_pi_notify` (
  `id`            int(11)       NOT NULL  AUTO_INCREMENT PRIMARY KEY,
  `instrument`    varchar(15)   DEFAULT NULL        COMMENT 'Instrument name',
  `semid`         varchar(15)   DEFAULT NULL        COMMENT 'Semester and program ID',
  `utdate`        date          DEFAULT NULL        COMMENT 'UT date of observation'
  `level`         integer       DEFAULT NULL        COMMENT 'Data processing level'
  `pi_email`      varchar(64)   DEFAULT NULL        COMMENT 'PI email used for notification'
  `last_mod`      datetime      DEFAULT CURRENT_TIMESTAMP  COMMENT 'Time of last modification'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;

CREATE TABLE IF NOT EXISTS `koa_summary` (
  `id`                           int(11)       NOT NULL  AUTO_INCREMENT PRIMARY KEY,
  `instrument`                   varchar(15)   DEFAULT NULL        COMMENT 'Instrument name',
  `utdate`                       date          DEFAULT NULL        COMMENT 'UT date of summary',
  `service`                      varchar(15)   DEFAULT NULL        COMMENT 'Instrument service name',
  `level0_files`                 int(11)       DEFAULT NULL        COMMENT 'Total number of level 0 KOAIDs',
  `level0_files_reprocessed`     int(11)       DEFAULT NULL        COMMENT 'Total number of level 0 KOAIDs',
  `level0_science_files`         int(11)       DEFAULT NULL        COMMENT 'Total number of level 0 science KOAIDs',
  `level0_calibration_files`     int(11)       DEFAULT NULL        COMMENT 'Total number of level 0 calibration KOAIDs',
  `level0_exposure_time`         double        DEFAULT NULL        COMMENT 'Total exposure time of all KOAIDs',
  `level0_science_exposure_time` double        DEFAULT NULL        COMMENT 'Total exposure time for science KOAIDs',
  `level0_total_dep_time`        double        DEFAULT NULL        COMMENT 'Total seconds of level 0 DEP processing',
  `level0_total_xfr_time`        double        DEFAULT NULL        COMMENT 'Total seconds of level 0 data transfer',
  `level0_total_ingest_time`     double        DEFAULT NULL        COMMENT 'Total seconds of level 0 data ingestion',
  `level0_total_time`            double        DEFAULT NULL        COMMENT 'Total seconds of level 0 end-to-end processing',
  `level0_total_size`            double        DEFAULT NULL        COMMENT 'Total size of level 0 data in MB',
  `level1_files`                 int(11)       DEFAULT NULL        COMMENT 'Total number of level 1 KOAIDs',
  `level1_total_size`            double        DEFAULT NULL        COMMENT 'Total size of level 1 data in MB',
  `level1_total_dep_time`        double        DEFAULT NULL        COMMENT 'Total seconds of level 1 DEP processing',
  `level1_total_xfr_time`        double        DEFAULT NULL        COMMENT 'Total seconds of level 1 data transfer',
  `level1_total_ingest_time`     double        DEFAULT NULL        COMMENT 'Total seconds of level 1 data ingestion',
  `level1_total_time`            double        DEFAULT NULL        COMMENT 'Total seconds of level 1 end-to-end processing',
  `level2_files`                 int(11)       DEFAULT NULL        COMMENT 'Total number of level 2 KOAIDs',
  `level2_total_size`            double        DEFAULT NULL        COMMENT 'Total size of level 2 data in MB',
  `level2_total_dep_time`        double        DEFAULT NULL        COMMENT 'Total seconds of level 2 DEP processing',
  `level2_total_xfr_time`        double        DEFAULT NULL        COMMENT 'Total seconds of level 2 data transfer',
  `level2_total_ingest_time`     double        DEFAULT NULL        COMMENT 'Total seconds of level 2 data ingestion',
  `level2_total_time`            double        DEFAULT NULL        COMMENT 'Total seconds of level 2 end-to-end processing',
  `last_mod`      datetime      DEFAULT CURRENT_TIMESTAMP  COMMENT 'Time of last modification'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;

CREATE TABLE IF NOT EXISTS `koa_storage` (
  `id`                    int(11)       NOT NULL  AUTO_INCREMENT PRIMARY KEY,
  `instrument`            varchar(15)   DEFAULT NULL        COMMENT 'Instrument name',
  `utdate`                date          DEFAULT NULL        COMMENT 'UT date of summary',
  `storage_type`          varchar(15)   DEFAULT NULL        COMMENT 'Storage type [AWS, SharePoint, stage]',
  `storage_location`      varchar(100)  DEFAULT NULL        COMMENT 'Storage location',
  `last_mod`              datetime      DEFAULT CURRENT_TIMESTAMP  COMMENT 'Time of last modification'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;

CREATE TABLE IF NOT EXISTS `odap_queue` (
  `filename`       varchar(250) NOT NULL COMMENT 'File to send to ODAP',
  `koaid`          varchar(48)           COMMENT 'Unique KOA ID',
  `level`          int(11)               COMMENT 'Data processing level',
  `creation_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'Time of last modification',
  UNIQUE `uidx` (`filename`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ;
