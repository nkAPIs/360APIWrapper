import asyncio
import logging
import os
from confighandler.src.configuration import Configuration

local_path = "./database.ini"
config_name = "360wrapper"

def get_configuration(debugmode:bool=True):
    logger = logging.getLogger(__name__)    
    logger.info("=======> get configuration!   <=======")
    ini_path = local_path
    config = Configuration(appname=config_name, debugging=debugmode, ini_file=ini_path)
    logger.info(f"Configuration loaded: {config}")
    logger.info("=======> Done <=======")
    return config

async def get_configuration_async():
    logger = logging.getLogger(__name__)    
    logger.info("=======> get configuration!   <=======")
    ini_path = local_path
    config = Configuration(appname=config_name, debugging=debugmode, ini_file=ini_path)
    logger.info(f"Configuration loaded: {config}")
    logger.info("=======> Done <=======")
    return config
