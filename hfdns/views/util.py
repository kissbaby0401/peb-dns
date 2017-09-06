import logging
import time
import subprocess
import os, signal,sys
import etcd
from flask import current_app
from ..extensions import db
from ..models import Server
import requests
import json
# current_app._get_current_object()


def getLogger(log_path):
    # logger初始化
    logger = logging.getLogger('DNS')
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path)
    formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger


def getRecordContent(record, prefix=None):
    #'修改前内容：'
    content = 'id: ' + str(record.id) + '\n' \
    + '记录主机: ' + str(record.host) + '\n' \
    + '记录类型: ' + str(record.record_type) + '\n' \
    + '记录值: ' + str(record.value) + '\n' \
    + 'TTL: ' + str(record.TTL) + '\n' \
    + '线路类型: ' + str(record.line_type) + '\n' \
    + '备注: ' + str(record.comment) + '\n' \
    + '创建人: ' + str(record.creator) + '\n' \
    + '创建时间: ' + str(record.create_time)

    if prefix:
        content = prefix + '\n' + content
    return content


def killProcesses(ppid=None):
    ppid = str(ppid)
    pidgrp = []
    def GetChildPids(ppid):
        command = "ps -ef | awk '{if ($3 ==%s) print $2;}'" % str(ppid)
        pids = os.popen(command).read()
        pids = pids.split()
        return pids
    pidgrp.extend(GetChildPids(ppid))
    for pid in pidgrp:
        pidgrp.extend(GetChildPids(pid))

    pidgrp.insert(0, ppid)
    while len(pidgrp) > 0:
        pid = pidgrp.pop()
        try:
            os.kill(int(pid), signal.SIGKILL)
            return True
        except OSError:
            try:
                os.popen("kill -9 %d" % int(pid))
                return True
            except Exception:
                return False



DEFAULT_CMD_TIMEOUT = 1200
def doCMDWithOutput(cmd, time_out = None):
    if time_out is None:
        time_out = DEFAULT_CMD_TIMEOUT
    # LOG.info("Doing CMD: [ %s ]" % cmd)
    pre_time = time.time()
    output = []
    cmd_return_code = 1
    cmd_proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

    while True:
        output_line = cmd_proc.stdout.readline().decode().strip("\r\n")
        cmd_return_code = cmd_proc.poll()
        elapsed_time = time.time() - pre_time
        if cmd_return_code is None:
            if elapsed_time >= time_out:
                killProcesses(ppid=cmd_proc.pid)
                # LOG.error("Timeout to exe CMD")
                return False
        elif output_line == '' and cmd_return_code is not None:
            break

        # sys.stdout.write("%s\n" % output_line)
        sys.stdout.flush()
        if output_line.strip() != '':
            output.append(output_line)
    return (cmd_return_code, output)



def initServer(cmd, app_object, server_id):
    with app_object.app_context():
        # print(server_id)
        current_server = Server.query.get(int(server_id))
        res = doCMDWithOutput(cmd)
        if not res:
            current_server.status = '初始化失败'
            current_server.logs = '超时！！初始化时间已超过20分钟'
            db.session.add(current_server)
            db.session.commit()
            return False, ['超时！！初始化时间已超过20分钟！']
        cmd_return_code, output = res
        if cmd_return_code != 0:
            print('\n'.join(output))
            current_server.status = '初始化失败'
            current_server.logs = '\n'.join(output)
            db.session.add(current_server)
            db.session.commit()
            return False, output
        else:
            print('\n'.join(output))
            current_server.status = 'ONLINE'
            current_server.logs = '\n'.join(output)
            db.session.add(current_server)
            db.session.commit()
            return True, output


class DNSRecord(object):

    def __init__(self, group, data, script):
        self.__group = group
        self.__data = data
        self.__script = script
        self.__create_url = current_app.config.get('DNSPOD_RECORD_BASE_URL') + 'Create'
        self.__modify_url = current_app.config.get('DNSPOD_RECORD_BASE_URL') + 'Modify'
        self.__delete_url = current_app.config.get('DNSPOD_RECORD_BASE_URL') + 'Remove'
        self.__body_info = {"login_token":current_app.config.get('DNSPOD_TOKEN'), "format": current_app.config.get('DNSPOD_DATA_FORMAT')}

    def create(self):
        if self.__group == 'outter':
            return self.__outter_execute(self.__create_url, self.__data)
        return doCMDWithOutput(self.__script)

    def modify(self):
        if self.__group == 'outter':
            return self.__outter_execute(self.__modify_url, self.__data)
        return doCMDWithOutput(self.__script)

    def delete(self):
        if self.__group == 'outter':
            return self.__outter_execute(self.__delete_url, self.__data)
        return doCMDWithOutput(self.__script)

    def __outter_execute(self, url, data):
        try:
            res = requests.post(url, data=dict(self.__body_info, **data))
            if res.status_code == 200:
                res_json = res.json()
                if res_json.get('status').get('code') == '1':
                    return 0, res_json
                return 1, [str(res_json)]
            return 1, [str(res_json)]
        except Exception as e:
            return 1, [e.__str__]

    def failHandler(self):
        pass

    def isDomainExists(self):
        pass




def getDNSPodLines(domain):
    body_info = {"login_token": current_app.config.get('DNSPOD_TOKEN'), "format": current_app.config.get('DNSPOD_DATA_FORMAT'), "domain": domain}
    try:
        res = requests.post(current_app.config.get('DNSPOD_LINE_URL'), data=body_info)
    except Exception as e:
        return []
    if res.status_code >= 200 and res.status_code <= 220:
        print(res.status_code)
        print(res.json())
        return res.json()['lines']
    return []


def getDNSPodTypes(domain):
    body_info = {"login_token": current_app.config.get('DNSPOD_TOKEN'), "format": current_app.config.get('DNSPOD_DATA_FORMAT'), "domain": domain}
    try:
        res = requests.post(current_app.config.get('DNSPOD_TYPE_URL'), data=body_info)
    except Exception as e:
        return []
    if res.status_code >= 200 and res.status_code <= 220:
        return res.json()['lines']
    return []




