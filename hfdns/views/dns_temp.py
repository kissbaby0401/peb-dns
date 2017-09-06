from jinja2 import Template
# from .util import dnsPod_token, data_format, base_Domain
from hfdns.extensions import db
from hfdns.models import User, View, Zone, Record, Logs
from sqlalchemy.sql import and_, or_, not_
import requests
import etcd
import copy
import time
from flask import current_app


def getETCDclient():
    client = etcd.Client(host=current_app.config.get('ETCD_SERVER_HOST'), port=current_app.config.get('ETCD_SERVER_PORT'))
    try:
        client.read(current_app.config.get('BIND_CONF'))
    except etcd.EtcdKeyNotFound:
        client.write(current_app.config.get('BIND_CONF'), '', prevExist=False)

    try:
        client.read(current_app.config.get('VIEW_DEFINE_CONF'))
    except etcd.EtcdKeyNotFound:
        client.write(current_app.config.get('VIEW_DEFINE_CONF'), '', prevExist=False)
    return client


def make_record(view_name, zone_name, record_list):
    etcd_client = getETCDclient()
    zone_record_conf = current_app.config.get('ZONE_BASE_DIR') + view_name + '/zone.' + zone_name
    zone_record_conf_content = Template(current_app.config.get('RECORD_TEMPLATE')).render(zone_name=zone_name, record_list=record_list)
    etcd_client.write(zone_record_conf, zone_record_conf_content, prevExist=True)
    time.sleep(0.2)


class DNSView(object):
    def __init__(self, view):
        self.view = view

    def create(self):
        self._make_view('create')

    def modify(self):
        self._make_view('modify')

    def delete(self):
        self._make_view('del')

    def _make_view(self, action):
        view_list = db.session.query(View).all()
        prevExist = True
        if action == 'create':
            prevExist = False

        etcd_client = getETCDclient()

        if action != 'modify':
            view_zone_conf = current_app.config.get('ETCD_BASE_DIR') + self.view.name + '/view.conf'
            view_zone_conf_content = Template(current_app.config.get('VIEW_TEMPLATE')).render(view_name=self.view.name)
            etcd_client.write(view_zone_conf, view_zone_conf_content, prevExist=prevExist)
            time.sleep(0.2)   #连续几个提交速度过快，etcd server检测不到提交

        acl_conf = current_app.config.get('ETCD_BASE_DIR') + self.view.name + '/acl.conf'
        acl_conf_content = Template(current_app.config.get('ACL_TEMPLATE')).render(view_name=self.view.name, ip_list=self.view.data.split())
        etcd_client.write(acl_conf, acl_conf_content, prevExist=prevExist)
        time.sleep(0.2)

        view_define_conf_content = Template(current_app.config.get('VIEW_DEFINE_TEMPLATE')).render(view_list=view_list)
        etcd_client.write(current_app.config.get('VIEW_DEFINE_CONF'), view_define_conf_content, prevExist=True)
        time.sleep(0.2)

        if action == 'del':
            view_base_dir = current_app.config.get('ETCD_BASE_DIR') + self.view.name
            etcd_client.delete(view_base_dir, recursive=True)
            time.sleep(0.2)


class DNSZone(object):
    def __init__(self, action, zone):
        self.zone = zone
        self.action = action
        self.__create_url = current_app.config.get('DNSPOD_DOMAIN_BASE_URL') + 'Create'
        self.__modify_url = current_app.config.get('DNSPOD_DOMAIN_BASE_URL') + 'Modify'
        self.__delete_url = current_app.config.get('DNSPOD_DOMAIN_BASE_URL') + 'Remove'

    def create(self):
        
        if self.zone.is_inner == 1 or self.zone.is_inner == 2:
            self.__create_inner()
        else:
            self.__create_outter()

    def modify(self, pre_views):
        if self.zone.is_inner == 1 or self.zone.is_inner == 2:
            self.__modify_inner(pre_views)
        else:
            self.__modify_outter()

    def delete(self):
        if self.zone.is_inner == 1 or self.zone.is_inner == 2:
            self.__del_inner()
        else:
            self.__del_outter()


    def __create_inner(self):
        # print('xxxxxxxxxxxxxxxxxxx')
        zone_list = db.session.query(Zone).filter(or_(Zone.is_inner == 1, Zone.is_inner == 2)).all()
        for z_view in self.zone.views.split(','):
            self._make_zone(self.action, z_view, zone_list, [])
            time.sleep(0.1)
    def __create_outter(self):
        # try:
        res = requests.post(self.__create_url, data=dict(login_token=current_app.config.get('DNSPOD_TOKEN'), domain=self.zone.name, format=current_app.config.get('DNSPOD_DATA_FORMAT')))
        if res.status_code == 200:
            res_json = res.json()
            if res_json.get('status').get('code') == '1':
                raise Exception(str(res_json))
        raise Exception(str(res_json))


    def __modify_inner(self, pre_views):
        zone_list = db.session.query(Zone).filter(or_(Zone.is_inner == 1, Zone.is_inner == 2)).all()
        current_views = set(self.zone.views.split(','))
        pre_views = set(pre_views)
        del_views = pre_views - current_views
        add_views = current_views - pre_views
        print(del_views)
        for d_view in del_views:
            self._make_zone('del', d_view, zone_list, [])
        for z_view in add_views:
            # records = db.session.query(Record).filter(Record.zone_id==self.zone.id, Record.line_type.in_(tuple(del_views))).all()
            record_list = db.session.query(Record).filter(Record.zone_id == self.zone.id, Record.line_type == z_view.strip(), Record.host != '@').all()
            self._make_zone(self.action, z_view, zone_list, record_list)

    def __modify_outter(self):
        raise Exception('外部域名不支持修改！')


    def __del_inner(self):
        zone_list = db.session.query(Zone).filter(or_(Zone.is_inner == 1, Zone.is_inner == 2)).all()
        for z_view in self.zone.views.split(','):
            self._make_zone(self.action, z_view, zone_list, [])
    def __del_outter(self):
        res = requests.post(self.__delete_url, data=dict(login_token=current_app.config.get('DNSPOD_TOKEN'), domain=self.zone.name, format=current_app.config.get('DNSPOD_DATA_FORMAT')))
        if res.status_code == 200:
            res_json = res.json()
            if res_json.get('status').get('code') != '1':
                # return 0, res_json
                raise Exception(str(res_json))
        raise Exception(str(res_json))


    def _make_zone(self, action, view_name, zone_list, record_list):
        etcd_client = getETCDclient()

        view_zone_conf = current_app.config.get('ETCD_BASE_DIR') + view_name + '/view.conf'
        # copy_zone_list = zone_list[:]
        if action == 'del':
            bind_zones = []
            for zz in zone_list:
                if view_name in zz.views.split(',') and zz.name != self.zone.name :
                    bind_zones.append(zz)
            view_zone_conf_content = Template(current_app.config.get('ZONE_TEMPLATE')).render(view_name=view_name, zone_list=bind_zones)
        else:
            bind_zones = []
            for zz in zone_list:
                if view_name in zz.views.split(','):
                    bind_zones.append(zz)
            view_zone_conf_content = Template(current_app.config.get('ZONE_TEMPLATE')).render(view_name=view_name, zone_list=bind_zones)
        etcd_client.write(view_zone_conf, view_zone_conf_content, prevExist=True)
        time.sleep(0.2)

        # view_zone_confiig 文件操作
        # forward only类型的zone，不生成 zone.xx.xx 文件
        # 修改zone不需要更改zone.xx.xx 文件
        if self.zone.z_type != 'forward only':
            zone_record_conf = current_app.config.get('ZONE_BASE_DIR') + view_name + '/zone.' + self.zone.name
            if action == 'create' or action == 'modify':
                zone_record_conf_content = Template(current_app.config.get('RECORD_TEMPLATE')).render(zone_name=self.zone.name, record_list=record_list)
                try:
                    etcd_client.write(zone_record_conf, zone_record_conf_content, prevExist=True)
                except etcd.EtcdKeyNotFound:
                    zone_record_conf_content = Template(current_app.config.get('RECORD_TEMPLATE')).render(zone_name=self.zone.name, record_list=[])
                    etcd_client.write(zone_record_conf, zone_record_conf_content, prevExist=False)

                time.sleep(0.2)
            if action == 'del':
                etcd_client.delete(zone_record_conf)
                time.sleep(0.2)


class DNSRecord(object):
    def __init__(self, record):
        self.record = record

    def create(self):
        pass

    def modify(self):
        pass

    def delete(self):
        pass

    # def __create_outter(self):
    #     pass

    # def __create_inner(self):
    #     pass

    # def __modify_outter(self):
    #     pass

    # def __modify_inner(self):
    #     pass

    # def __del_outter(self):
    #     pass

    # def __del_inner(self):
    #     pass



