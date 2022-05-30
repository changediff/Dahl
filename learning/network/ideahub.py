#!/usr/bin/env python
# -*- encoding=utf8 -*-

'''
Author: fasion
Created time: 2022-03-07 17:54:32
Last Modified by: fasion
Last Modified time: 2022-04-09 18:04:41
'''

import functools
import sqlite3
import threading
import traceback
import time

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)
from itsdangerous import (
    TimestampSigner,
)

SECRET_KEY = b'1234567890'

app = Flask(__name__)
app.secret_key = SECRET_KEY

def dict_factory(cursor, row):
    d = {}
    for i, col in enumerate(cursor.description):
        d[col[0]] = row[i]
    return d

thread_locals = threading.local()
def getdb():
    db = getattr(thread_locals, 'db', None)
    if db:
        return db

    thread_locals.db = db = sqlite3.connect('ideahub.db')
    db.row_factory = dict_factory

    return db

def catch_exception(handler):
    @functools.wraps(handler)
    def proxy(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except Exception as e:
            msg = traceback.format_exc()
            print(msg)
            return render_template('message.html', msg=msg, msgtype='fail')

    return proxy

def ensure_db_cursor(handler):
    @functools.wraps(handler)
    def proxy(*args, **kwargs):
        db = getdb()
        cursor = db.cursor()
        try:
            return handler(*args, **kwargs, db=db, cursor=cursor)
        finally:
            cursor.close()

    return proxy

def ensure_login(handler):
    @functools.wraps(handler)
    @ensure_db_cursor
    def proxy(db, cursor, *args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return redirect('/login')

        cursor.execute('SELECT * FROM Users where id=?', (user_id,))
        for user in cursor.fetchall():
            return handler(*args, current_user=user, db=db, cursor=cursor, **kwargs)

        return redirect('/login')

    return proxy

signer = TimestampSigner(SECRET_KEY)

def current_user_id_in_bytes():
    user_id = session.get('user_id')
    return str(user_id).encode()

def new_csrf_token():
    return signer.sign(current_user_id_in_bytes()).decode()

def validate_csrf_token(token, max_age=None):
    try:
        return signer.unsign(token, max_age=max_age) == current_user_id_in_bytes()
    except:
        return False

@app.context_processor
def utility_processor():
    return dict(new_csrf_token=new_csrf_token)

@app.route("/login", methods=['GET', 'POST'])
@catch_exception
@ensure_db_cursor
def login(db, cursor):
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        userpass = request.form['userpass']

        sql = 'SELECT * FROM Users where username="{}" and userpass="{}"'.format(
            username,
            userpass,
        )
        print("SQL: {}".format(sql))

        cursor.execute(sql)
        for user in cursor.fetchall():
            session['user_id'] = user['id']
            return redirect('/')
        else:
            msg = 'Username or password is wrong!'

    return render_template("login.html", msg=msg, msgtype="fail")

@app.route("/logout", methods=['GET', 'POST'])
@catch_exception
def logout():
    session.pop('user_id', None)
    return redirect('/')

@app.route("/", methods=['GET', 'POST'])
@catch_exception
@ensure_login
def home(current_user, db, cursor):
    if request.method == 'POST':
        cursor.execute('INSERT INTO Ideas (content, introducer_id, introduced_ts) values (?, ?, ?)', (
            request.form['content'].strip(),
            current_user['id'],
            int(time.time()),
        ))
        db.commit()
        return redirect('/')

    introducer_id = request.args.get('introducer_id')
    if introducer_id:
        cursor.execute('SELECT Ideas.*, username as introducer_username FROM Ideas LEFT JOIN Users Where Ideas.introducer_id=Users.id AND Users.id=? ORDER BY introduced_ts DESC', (introducer_id,))
    else:
        cursor.execute('SELECT Ideas.*, username as introducer_username FROM Ideas LEFT JOIN Users Where Ideas.introducer_id=Users.id ORDER BY introduced_ts DESC')
    ideas = cursor.fetchall()

    return render_template('home.txt', current_user=current_user, ideas=ideas)

@app.route("/rank", methods=['GET'])
@catch_exception
@ensure_login
def rank(current_user, db, cursor):
    cursor.execute('SELECT * FROM Users ORDER BY coins DESC, username ASC')
    users = cursor.fetchall()
    return render_template('rank.html', current_user=current_user, users=users)

@app.route("/delete-idea/<idea_id>", methods=['POST'])
@catch_exception
@ensure_login
def delete_idea(idea_id, current_user, db, cursor):
    cursor.execute('SELECT * FROM Ideas WHERE id=? AND introducer_id=?', (int(idea_id), current_user['id']))
    if not cursor.fetchall():
        return render_template('message.html', msg='Idea not found or not yours', msgtype='fail')

    if cursor.execute('DELETE FROM Ideas WHERE id=?', (int(idea_id), )).rowcount:
        db.commit()
        return redirect('/')
    else:
        return render_template('message.html', msg='Idea not exists', msgtype='fail')

@app.route("/reward", methods=['GET', 'POST'])
@catch_exception
@ensure_login
def reward(current_user, db, cursor):
    receiver_id = request.args.get('receiver_id')
    if not receiver_id:
        return render_template('message.html', current_user=current_user, msg='No receiver id', msgtype="fail")

    cursor.execute('SELECT * FROM Users WHERE id=?', (int(receiver_id),))
    receivers = cursor.fetchall()
    if not receivers:
        return render_template('message.html', current_user=current_user, msg='Bad receiver id: {}'.format(receiver_id), msgtype="fail")

    receiver = receivers[0]

    if request.method == 'GET':
        return render_template('reward.html', current_user=current_user, receiver=receiver)

    # if not validate_csrf_token(request.form.get('csrf_token')):
    # 	return render_template('reward.html', current_user=current_user, receiver=receiver, msg="CSRF token is not valid!", msgtype="fail")

    coins = int(request.form.get('coins'))
    if coins <= 0:
        return render_template('reward.html', current_user=current_user, receiver=receiver, msg="Coins not valid!", msgtype="fail")

    if current_user['coins'] < coins:
        return render_template('reward.html', current_user=current_user, receiver=receiver, msg="Coins not enough", msgtype="fail")

    result = cursor.execute('UPDATE Users Set coins=coins-? WHERE id=? AND coins>=?', (coins, current_user['id'], coins))
    if not result.rowcount:
        return render_template('reward.html', current_user=current_user, receiver=receiver, msg="Coins not enough", msgtype="fail")

    cursor.execute('UPDATE Users Set coins=coins+? WHERE id=?', (coins, receiver['id']))
    if not result.rowcount:
        return render_template('reward.html', current_user=current_user, receiver=receiver, msg="Coin transfer failed", msgtype="fail")

    db.commit()

    current_user['coins'] -= coins

    return render_template('reward.html', current_user=current_user, receiver=receiver, msg="{} coins rewarded to {} successfully".format(coins, receiver['username']), msgtype="success")

@app.route("/api/ideas", methods=['GET'])
@catch_exception
@ensure_login
def fetch_ideas(current_user, db, cursor):
    introducer_id = request.args.get('introducer_id')
    if introducer_id:
        cursor.execute('SELECT Ideas.*, username as introducer_username FROM Ideas LEFT JOIN Users Where Ideas.introducer_id=Users.id AND Users.id=? ORDER BY introduced_ts DESC', (introducer_id,))
    else:
        cursor.execute('SELECT Ideas.*, username as introducer_username FROM Ideas LEFT JOIN Users Where Ideas.introducer_id=Users.id ORDER BY introduced_ts DESC')

    ideas = cursor.fetchall()
    return jsonify(ideas)


@app.route("/list", methods=['GET'])
@catch_exception
@ensure_login
def list(current_user, db, cursor):
    return render_template('list.html', current_user=current_user)