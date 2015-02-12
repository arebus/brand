#!/usr/bin/python

import sys
reload(sys)  
sys.setdefaultencoding('utf8')
import time
import MySQLdb as db
from warnings import filterwarnings
import _mysql_exceptions
import xml.etree.ElementTree as ET
import xml.dom.minidom
import logging
#from optparse import OptionParser
import argparse

import os
import glob

xmlRootList = {}

connectionList = {}
replaceDictionary={}
action_path='actions/'



# DictCursor
# 0 - name
COLUMN_NAME=0
# 1 - type
COLUMN_TYPE=1


def close_db_connections():
  for _connection_name in connectionList.keys():
    logging.debug("Close DB connection %s", _connection_name)
    _connect = connectionList[_connection_name]
    _connect.close()
    return

def exit_error():
  logging.debug("Exit on error")
  close_db_connections()
  exit(0)
  return

def replaceKeywords(_text_replace, _replace_dict):
  _text = _text_replace
  for _key in _replace_dict:
    _text = _text.replace(_key, str(_replace_dict[_key]))
  return _text

# prettifying xml (from https://norwied.wordpress.com/2013/08/27/307/)
def indent(elem, level=0):
  i = "\n" + level*"  "
  if len(elem):
    if not elem.text or not elem.text.strip():
      elem.text = i + "  "
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
    for elem in elem:
      indent(elem, level+1)
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
  else:
    if level and (not elem.tail or not elem.tail.strip()):
      elem.tail = i

#======================================================================
# Action types

actionOpenDBConnection = 'openDBConnection'
actionExportSQLDataToXML = 'exportSQLDataToXML'
actionExecuteSQL = 'executeSQL'
actionWriteXML = 'writeXML'
actionLoadSQLDataFromXML = 'loadSQLDataFromXML'

#======================================================================

def openDBConnection(_conn_name, _host, _port, _user_name, _password, _database):
  logging.debug("conn_name=%s, host=%s, port=%s, user_name=%s, password=%s, database=%s", _conn_name, _host, _port, _user_name, _password, _database)
  try:
    _conn = db.connect(host=_host,
                       port=_port,
                       user=_user_name, 
                       passwd=_password, 
                       db=_database) 
    connectionList[_conn_name] = _conn
  except db.Error as e:
    logging.error(str(e))
    exit_error()
  return

def exportSQLDataToXML(_conn_name, _table_name, _file_name, _sql):
#  def _SQLRowToXML(_col_name, _col_value):
    
#    return
  if not xmlRootList.has_key(_file_name):
    xmlRootList[_file_name] = ET.Element('configuration')
  try:    
    _conn = connectionList[_conn_name] # Get connection from dict
    _cur = _conn.cursor(db.cursors.DictCursor)
    _stmt = replaceKeywords(_sql, replaceDictionary)
    _cur.execute(_stmt)
    logging.debug("Original query %s", _sql)
    logging.debug("Query After replace %s", _stmt)
    _rows = _cur.fetchall()
    # col_names = [i[0] for i in _cur.description]
    _elem_table = ET.SubElement(xmlRootList[_file_name], str(_table_name))
    for _row in _rows:
      _row_element = ET.SubElement(_elem_table, 'row')
      for _column in _cur.description:
        _column_value = _row[_column[COLUMN_NAME]]
  # boolean what is bit
        if _column[COLUMN_TYPE] == 16:
          if _column_value == '\x01':
            _column_value = '1'
          elif _column_value == '\x00':
            _column_value = '0'
        _column_element = ET.SubElement(_row_element, str(_column[COLUMN_NAME]))
        _column_element.text = str(_column_value)
        logging.debug(" Row %s(%s)", _column, _column_value)
  except db.Error as e:
    logging.error(str(e))
    exit_error()
  return

def executeSQL(_conn_name, _sql):
  logging.debug("Inside executeSQL")
  _stmt = replaceKeywords(_sql, replaceDictionary)
#  logging.debug("Original statement: %", _sql)
  try:    
    _conn = connectionList[_conn_name] # Get connection from dict
    _cur = _conn.cursor(db.cursors.DictCursor)
#    logging.debug("Statement to execute: %", _stmt)
    _cur.execute(_stmt)
  except db.OperationalError, e:
    logging.error(str(e))
    exit_error()
  except db.ProgrammingError, e:
    logging.error(str(e))
    exit_error()

  return


def writeXML(_file_name):
  indent(xmlRootList[_file_name])
  _tree = ET.ElementTree(xmlRootList[_file_name])
  _tree.write(_file_name, xml_declaration=True, encoding='utf-8', method="xml")
  return

def loadSQLDataFromXML(_file_name, _conn_name):
  _conn = connectionList[_conn_name] # Get connection from dict
  _cur = _conn.cursor(db.cursors.DictCursor)
  _tablePrefix = "temp_"
  _tree = ET.parse(_file_name)
  _root = _tree.getroot()
  logging.debug("Inside loadSQLDataFromXML")
  for _config in _root.iter('configuration'):
    for _table in _config:
      for _tableRow in _table.iter('row'):
        _insertStr = "insert into " + _tablePrefix + _table.tag + "("
        _valuesStr = " values ("
        for _row in _tableRow:
          _val = _row.text
          if _val is None:
            _val=""
          _insertStr = _insertStr + "`" + _row.tag + "`" + ","
          _valuesStr = _valuesStr + "'" + _val + "'" + ","
        _insertStr = _insertStr[:-1]+")"
        _valuesStr = _valuesStr[:-1]+");"
        _sqlstmt = _insertStr + _valuesStr
        logging.debug("Original query: %s", _sqlstmt)
        _sqlstmt = replaceKeywords(_sqlstmt, replaceDictionary)
        logging.debug("Query after replace: %s ", _sqlstmt)
        _cur.execute(_sqlstmt)
  return


def _readArgsFromXMLs(_action_parser):
  _action_file_ext=['xml']
  _action_files = [fname for fname in os.listdir(action_path) if any([fname.endswith(ext) for ext in (_action_file_ext) ])];
#  logging.debug("Actoin files %s ", _action_files)
  for _action_file in _action_files:
    _action_name = _action_file[:-4]
    try:
      _tree = ET.parse(action_path+_action_file)
    except IOError, e:
      logging.error("There is no action file %s", _action_file)
      exit(0)
    _root = _tree.getroot()
    for _options in _root.iter('options'):
      _new_action_parser = _action_parser.add_parser(str(_action_name), help=_options.get('help'), description=_options.get('description'))
      
      for _option in _options:
	if _option.get('action') is not None:
	  _arg = _new_action_parser.add_argument(_option.get('name'), help=_option.get('help'), action=_option.get('action'))
	else:
	  _arg = _new_action_parser.add_argument(_option.get('name'), help=_option.get('help'))
	if _option.get('type') is not None:
	  _arg.type = eval(_option.get('type'))
	if _option.get('required') is not None:
	  _arg.required = _option.get('required')
	if _option.get('default') is not None:
	  _default_val = _option.get('default')
	  if _default_val.upper() == 'TRUE':
	    _default_val = True
	  elif _default_val.upper() == 'FALSE':
	    _default_val = False
	  _arg.default = _default_val
  return 



def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("-s", "--silent",
                    action="store_true", dest="silent", default=False,
                    help="[TO DO] Silent mode. Don't output anything but errors")
  parser.add_argument("--log-level",
                    action="store", dest="log_level", choices=('DEBUG', 'INFO', 'WARNING'),
                    help="Logging level")
  actions_arg_parser = parser.add_subparsers(help="Available actions", dest="action")
  _readArgsFromXMLs(actions_arg_parser)
  arguments = parser.parse_args()
  varguments = vars(arguments)
  for varg in varguments:
    _dict_key = "{"+varg+"}"
    replaceDictionary[_dict_key] = varguments[varg]

  # lets start
  actionfile = action_path+arguments.action + ".xml"
  logging.basicConfig(level=arguments.log_level)
  
  logging.debug("Action file: %s", actionfile)
  logging.debug("Arguments: %s", arguments)
  logging.debug("Dictionary: %s", replaceDictionary)

  filterwarnings('ignore', category = db.Warning)

  # Its bad idea. Needs to be done in some other way
  
  try:
    tree = ET.parse(actionfile)
  except IOError, e:
          logging.error("There is no action with name %s", actionfile)
          exit(0)
      
  root = tree.getroot()
  
  totalStepsCount = root.__len__()
  stepCounter = 1

  replaceDictionary[':date_YYYYMMDD'] = str(time.strftime("%Y%m%d"))
  
  print "Start " + replaceKeywords(root.get('description'), replaceDictionary)
  
  for step in root.iter('step'):
    action_type = step.get('action_type')
    step_description = replaceKeywords(step.get('description'), replaceDictionary)
    if step_description is None:
      logging.error("Action type %s have attribute %s", action_type, step_description)
      exit(0)
    print "Step " + stepCounter.__str__() + " of " + totalStepsCount.__str__() + ": " + step_description
# Do actionOpenDBConnection
    if action_type == actionOpenDBConnection:
      logging.info("Action type = openDBConnection")
      host = step.find('host').text
      port = int(step.find('port').text)
      user_name = step.find('user_name').text
      password = step.find('password').text
      database = step.find('database').text
      openDBConnection(_conn_name=step.get('connection_name'), _host=host, _port=port, _user_name=user_name, _password=password, _database=database)
# Do actionImportSQLDataToXML
    elif action_type == actionExportSQLDataToXML:
      logging.info("Action type = exportSQLDataToXML")
      file_name = replaceKeywords(step.get('file_name'), replaceDictionary) 
      exportSQLDataToXML(step.get('connection_name'), step.get('table_name'), file_name, step.find('query').text)
# Do actionExecuteSQL
    elif action_type == actionExecuteSQL:
      logging.info("Action type = executeSQL")
      executeSQL(step.get('connection_name'), step.find('query').text)
# Do actionWriteXML
    elif action_type == actionWriteXML:
      logging.debug("Action type = writeXML")
      file_name = replaceKeywords(step.get('file_name'), replaceDictionary) 
      writeXML(file_name)
# Do actionLoadSQLDatFromXML
    elif action_type == actionLoadSQLDataFromXML:
      logging.info("Action type = loadSQLDataFromXML")
      file_name = replaceKeywords(step.get('file_name'), replaceDictionary)
      loadSQLDataFromXML(file_name, step.get('connection_name'))
      
    stepCounter = stepCounter+1

  print("Done")
  
if __name__ == "__main__":
  main()
  