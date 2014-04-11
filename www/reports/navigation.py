#!/usr/bin/env python

import sys
sys.path.append('..')
import os
import sqlite3
import re
import sys
import functions as f
from functions.wsgi_handler import wsgi_response
from render_template import render_template
from philologic import HitWrapper
import json

philo_types = set(['div1', 'div2', 'div3'])

def navigation(environ,start_response):
    db, dbname, path_components, q = wsgi_response(environ,start_response)
    path = os.getcwd().replace('functions/', '')
    obj = db[path_components]
    if q['format'] == "json":
        obj_text = f.get_text_obj(obj, path, query_args=q['byte'])
        return json.dumps(obj_text)
    if obj.philo_type == 'doc':
        return render_template(obj=obj,philo_id=obj.philo_id[0],dbname=dbname,f=f,navigate_doc=navigate_doc,
                       db=db,q=q,template_name='t_o_c.mako', report="t_o_c")
    obj_text = f.get_text_obj(obj, path, query_args=q['byte'])
    prev = ' '.join(obj.prev.split()[:7])
    next = ' '.join(obj.next.split()[:7])
    return render_template(obj=obj,philo_id=obj.philo_id[0],dbname=dbname,f=f,navigate_doc=navigate_doc,
                       db=db,q=q,obj_text=obj_text,prev=prev,next=next,
                       template_name='object.mako', report="navigation")

def navigate_doc(obj, db):
    conn = db.dbh 
    c = conn.cursor()
    query =  str(obj.philo_id[0]) + " _%"
    c.execute("select philo_id, philo_name, philo_type, byte_start from toms where philo_id like ?", (query,))
    text_hierarchy = []
    for id, philo_name, philo_type, byte in c.fetchall():
        if philo_type not in philo_types or philo_name == '__philo_virtual':
            continue
        else:
            text_hierarchy.append(db[id])
    return text_hierarchy
    
def get_neighboring_pages(db, doc_id, doc_page):
    conn = db.dbh
    c = conn.cursor()
    c.execute('select philo_seq from pages where n=? and philo_id like ?', (doc_page, doc_id))
    philo_seq = c.fetchone()[0]
    prev_seq = philo_seq - 1
    c.execute('select n from pages where philo_seq=? and philo_id like ?', (prev_seq, doc_id))
    try:
        prev_page = c.fetchone()[0]
    except TypeError:  ## There is no previous page in that doc
        prev_page = None
    next_seq = philo_seq + 1
    c.execute('select n from pages where philo_seq=? and philo_id like ?', (next_seq, doc_id))
    try:
        next_page = c.fetchone()[0]
    except TypeError:  ## There is no previous page in that doc
        next_page = None
    return prev_page, next_page

def has_pages(obj, db):
    conn = db.dbh
    c = conn.cursor()
    ## this query will be slow until we create a doc id field
    c.execute('select n from pages where philo_id like ?', (str(obj.philo_id[0]) + ' %', ))
    if c.fetchall(): ## This document has pages
        return True
    else:
        return False
    
def get_page_num(obj, db):
    philo_id = ' '.join([str(i) for i in obj.philo_id])
    conn = db.dbh
    c = conn.cursor()
    c.execute('select page from toms where philo_id = ?', (philo_id,))
    try:
        return str(c.fetchone()[0] + 1)
    except TypeError:
        try:
            return c.fetchone()[0]
        except:
            return None