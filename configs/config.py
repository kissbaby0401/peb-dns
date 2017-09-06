'''
Created on Mar 14, 2017

@author: zeke
'''

import os
root_dir = os.path.abspath(os.path.dirname(__file__))

class Config:
    
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hfdns_author_lijiajia'
    ROOT_DIR = root_dir

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):

    @classmethod
    def init_app(cls, app):

        # log to syslog
        import logging
        from logging.handlers import SysLogHandler
        syslog_handler = SysLogHandler()
        syslog_handler.setLevel(logging.WARNING)
        app.logger.addHandler(syslog_handler)
        
        
config = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig,
    'default': DevelopmentConfig
}

config_pyfiles = {
    'dev': 'configs/dns_dev.cfg',
    'prod': 'configs/dns_prod.cfg',
    'default': 'configs/dns_dev.cfg'
}
