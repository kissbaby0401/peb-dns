PEB-DNS 管理平台
===========================
该项目用于公司内部多 IDC 的 DNS 管理
****
### Author: 运维团队出品
### E-mail: ml_12383@pingan.com.cn
****

# 平台架构图如下：

![dns](/dns.jpg "DNS 平台架构图")

功能介绍
------

#### 1， DNS 管理方式：

公司使用 BIND 搭建 DNS 服务器。

平台使用 ETCD 来管理 DNS 服务器的 BIND 配置文件，包括 VIEW，ZONE，RECORD 的各个配置文件。

所有的 DNS 服务器的配置文件和数据都是统一从 ETCD 上获取，因此所有 DNS 服务器的配置文件及数据都是相同的，且所有 DNS 服务器类型均为 master，不存在 slave。

当再平台上对 DNS 进行操作时，只要配置文件有变化，所有服务器均能从 ETCD 上获取最新的配置文件。

#### 2，使用技术栈：

后端： Python3.5 + Flask + Sqlalchemy + Mysql

前端： 基于开源 UI AdminLTE + Bootstrap + Jquery


#### 3，功能简介

* DNS 服务器管理

* BIND 主配置文件管理

* View 管理

* Zone 管理

* Record 管理

    * 内网域名 Record 管理

    * 劫持域名 Record 管理

    * 公网域名 Record 管理

* 平台权限管理

* 操作记录


#### 4，环境搭建

* 本教程基于 Ubuntu/Debian，已安装 python3 环境的请跳过

* 克隆项目代码到本地
```bash
# 将代码仓库 clone 到本地
git clone xxx@xxx:haofang/hfdns.git
```

* 工具安装
```bash
# 安装 python3 环境
sudo apt-get update
sudo apt-get install python3-pip python3-dev
sudo apt-get install build-essential libssl-dev libffi-dev python-dev

#安装 virtualenv
sudo pip3 install virtualenv virtualenvwrapper
echo "export VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3" >> ~/.bashrc
echo "export WORKON_HOME=~/Env" >> ~/.bashrc
echo "source /usr/local/bin/virtualenvwrapper.sh" >> ~/.bashrc
source ~/.bashrc

# 现在你的 home 目录下有 Env 的文件夹，你的 python 虚拟环境都会创建在这里

mkvirtualenv hfdns_env # hfdns 可随便改成你的项目名
workon hfdns_env # 现在已进入项目的独立环境


# 安装 mysql 略  （请安装 mysql5.7 版本）
sudo apt-get install mysql-server
# 安装 etcd 略  （请参考官方文档）
sudo apt-get install etcd

```

* 安装依赖

首先进入当前目录下
```bash
workon hfdns_env # 现在已进入项目的独立环境
pip install -r requirements.txt

# 下载页面 https://dev.mysql.com/downloads/connector/python/
# 选择 Platform Independent, 下载 mysql 驱动 mysql-connector-python==2.1.6
# 解压后，进入文件夹然后运行

python setup.py install

```


* 初始化数据库

1，创建数据库
```bash
# 进入当前项目根目录下
❯ mysql -u root -p

mysql> create database <your_db_name>;
Query OK, 1 row affected (0.01 sec)

mysql> ^DBye
```

2，当前目录下修改配置文件
dns_dev.cfg（开发环境配置文件）
dns_prod.cfg （生产环境配置文件）
配置你的 mysql 地址

3，修改配置文件

修改 env.sh
```bash
export FLASK_DEBUG=1     #部署开发环境，请将参数改为 dev
export FLASK_DEBUG=0     #部署生产环境，请将参数改为 prod
```

修改 hf_dns.py
```bash
app = create_app('dev')     #部署开发环境，请将参数改为 dev
app = create_app('prod')    #部署生产环境，请将参数改为 prod
```

4，初始化数据库
```bash
source env.sh
flask db init
flask db migrate
flask db upgrade
```


#### 简单快速部署方式

创建 nginx 配置

`sudo vim /etc/nginx/sites-enabled/hfdns.conf`

```nginx
server {
    listen 80;
    server_name hfdns.xxx.com; # 这是 HOST 机器的外部域名，用地址也行

    location / {
        proxy_pass http://127.0.0.1:8080; # 这里是指向 gunicorn host 的服务地址
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

  }
```
然后重新启动 nginx
sudo service nginx restart


进入当前项目根目录下，运行以下命令部署
```bash
workon hfdns_env
nohup gunicorn -w 4 hf_dns:app -b 0.0.0.0:8080 --log-level=debug &
```
PS: 上面 -w 为 开启 workers 数，公式：（系统内核数*2 + 1)



#### 推荐部署方式
```bash
# 安装 supervisor
sudo apt-get install supervisor

```
创建 supervisor 配置

`sudo vim /etc/supervisor/conf.d/hfdns.conf`
```
[program:hfdns_env]
command=/root/Env/hfdns_env/bin/gunicorn
    -w 3
    -b 0.0.0.0:8080
    --log-level debug
    "application.app:create_app()"                             ; 默认启动 dev 环境，如要启动生产环境，请改为 create_app('prod')

directory=/opt/py-maybi/                                       ; 你的项目代码目录
autostart=false                                                ; 是否自动启动
autorestart=false                                              ; 是否自动重启
stdout_logfile=/opt/logs/gunicorn.log                          ; log 日志
redirect_stderr=true
```
PS: 上面 -w 为 开启 workers 数，公式：（系统内核数*2 + 1)

创建 nginx 配置

`sudo vim /etc/nginx/sites-enabled/hfdns.conf`

```nginx
server {
    listen 80;
    server_name hfdns.xxx.com; # 这是 HOST 机器的外部域名，用地址也行

    location / {
        proxy_pass http://127.0.0.1:8080; # 这里是指向 gunicorn host 的服务地址
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

  }
```

接着启动 supervisor, nginx
```bash
sudo supervisorctl reload
sudo supervisorctl start hfdns_env

sudo service nginx restart
```


