import re
import time
import datetime
import pymongo
from tqdm import tqdm
import copy
from loguru import logger

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from selenium.common.exceptions import NoSuchElementException,StaleElementReferenceException,TimeoutException


class Tweet:

    def __init__(self, query, uid, ptime, pcontent, padditional, nb_reply, nb_retweet, nb_favorite):
        self.query = query
        self.uid = uid
        self.ptime = ptime
        self.pcontent = pcontent
        self.padditional = padditional  # 转发推文，文章链接，图片，视频
        self.nb_retweet = nb_retweet  # nbr of retweet
        self.nb_favorite = nb_favorite  # nbr of favorite
        self.nb_reply = nb_reply  # nbr of reply

    def __repr__(self):
        return "Tweet={}\nQuery={}".format(self.pcontent, self.query)


class User:

    def __init__(self, profile_url):
        self.profile_url = profile_url
        self.ID = profile_url.split('/')[-1]
        self.name = ''
        self.avatar = ''
        self.query = ''  # query相关的大V用户
        self.intro = ''

    def __repr__(self):
        return "User {}".format(self.ID)


def compare_time(time1, time2):
    s_time = time.mktime(time.strptime(time1, '%Y年%m月%d日'))
    e_time = time.mktime(time.strptime(time2, '%Y年%m月%d日'))
    return int(s_time) - int(e_time)


def convert_time(x):
    '''
    for x in ['20分钟','1小时','1天', '10月10日','2018年10月1日']:
        print(convert_time(x))
    '''
    now = datetime.datetime.now()
    pattern = r'\d{4}年\d+月\d+日'
    if re.match(pattern, x):
        return x
    pattern = r'\d+月\d+日'
    if re.match(pattern, x):
        return "{}年".format(now.year) + x
    return "{}年{}月{}日".format(now.year, now.month, now.day)


def is_non_result(browser):
    '''
    判断结果是否为空
    '''
    #     result_div_xpath = "//div[@id='react-root']"
    #     wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
    #     try:
    #         result_div = browser.find_element_by_xpath(result_div_xpath)
    #         return "未找到结果" in result_div.text
    #     except NoSuchElementException as e:
    return "未找到结果" in browser.find_element_by_tag_name('body').text


def get_search_input_v1(browser):
    # 定位搜索框
    search_input_xpath = "//input[@placeholder='Search Twitter']"
    wait.until(EC.presence_of_element_located((By.XPATH, search_input_xpath)))
    search_input = browser.find_element_by_xpath(search_input_xpath)
    return search_input

def extract_reply_retweet_favorite(element):
    t = []
    for x in element.find_elements_by_xpath('./div')[:3]:
        if x.text.strip() == '':
            t.append(0)
        else:
            t.append(int(x.text.strip()))
    return tuple(t)

#### query -> 推文爬取
def parse_tweet_result_div(result_div, query):
    count = 0
    for div in result_div:
        user, tweet = div.find_elements_by_xpath('./div')
        profile_url = user.find_element_by_tag_name(
            'a').get_attribute('href').strip()
        uid = profile_url.split('/')[-1] # 获取发帖用户id
        a, *b_c, d = tweet.find_elements_by_xpath('./div')  # 按照div分为>=3层
        # 获取发帖时间
        ptime = a.find_elements_by_tag_name('a')[-1].text
        ptime = convert_time(ptime)
        nb_reply, nb_retweet, nb_favorite = 0, 0, 0
        # try:
        #     nb_reply, nb_retweet, nb_favorite = extract_reply_retweet_favorite(
        #         d)
        # except:
        #     nb_reply, nb_retweet, nb_favorite = 0, 0, 0
        # pcontent = b_c[0].text
        padditional = []
        if len(b_c) > 1:
            for x in b_c[1:]:
                try:
                    a = x.find_element_by_tag_name('a').get_attribute('href')
                    padditional.append(a)
                except NoSuchElementException as e:
                    padditional.append(x.text.strip())

        pcontent = []
        # 获取发帖文本内容
        for div in d.find_elements_by_xpath('./div'):
            tmp = []
            for span in div.find_elements_by_tag_name('span'):
                tmp.append(span.text)
            pcontent.append(tmp)

        user = User(profile_url)
        tweet = Tweet(query, uid, ptime, pcontent, padditional,
                      nb_reply, nb_retweet, nb_favorite)
        # save to databse
        user_dict = user.__dict__
        user_dict['_id'] = user_dict['ID']
        if user_table.update_one({'_id': user_dict['_id']}, {'$set': user_dict},
                                 upsert=True) and tweet_table.insert_one(tweet.__dict__):
            count += 1
        # if user_table.insert_one(user.__dict__) and tweet_table.insert_one(tweet.__dict__):
        #     count += 1
    return count


def crawl_tweet(browser, query):
    count = 0
    result_div_xpath = '//div[@data-testid="tweet"]'
    wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
    result_div = browser.find_elements_by_xpath(result_div_xpath)
    last_div = result_div[-1]
    # 解析结果
    count += parse_tweet_result_div(result_div, query)
    while count < MAX_TWEET_SIZE:
        #         logger.info("{}/{}".format(count,MAX_TWEET_SIZE))
        result_div_xpath = '//div[@data-testid="tweet"]'
        wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
        result_div = browser.find_elements_by_xpath(result_div_xpath)
        last_div = result_div[-1]
        try:
            count += parse_tweet_result_div(result_div, query)
        except StaleElementReferenceException as e:
            time.sleep(2)
            continue

        # 翻页
        try_times = 0
        old_height = browser.execute_script("return document.body.scrollHeight;")
        while True:
            browser.execute_script(
                'window.scrollTo(0,document.body.scrollHeight)')
            wait.until(EC.presence_of_element_located(
                (By.XPATH, result_div_xpath)))
            result_div = browser.find_elements_by_xpath(result_div_xpath)
            if result_div[-1] == last_div:
                try_times += 1
            if result_div[-1] != last_div:
                last_div = result_div[-1]
                break
            time.sleep(3)
            new_height = browser.execute_script("return document.body.scrollHeight;")
            if old_height == new_height:
                try_times += 1
                last_div = result_div[-1]
            if try_times >= 3:
                count = MAX_TWEET_SIZE  # 到头了停止翻页采集该query
                print('到头了')
                break


def search_tweet_from_query(browser, query_list, finish_query_list):
    '''
    更加query采集推文
    '''
    for query in tqdm(query_list):
        logger.info('query = {}'.format(query))
        browser.get('https://twitter.com/explore')

        # 定位搜索框
        if browser.current_url == 'https://twitter.com/explore':
            search_input = get_search_input_v1(browser)
        else:
            print('error')
            return
        # 搜索query
        search_input.clear()
        search_input.send_keys(query)
        search_input.send_keys(Keys.ENTER)

        # 获取结果
        if is_non_result(browser):
            bad_query_list.append(query)
            continue
        time.sleep(1)
        try:
            crawl_tweet(browser, query)
        except TimeoutException as e:
            print('TimeoutException')
            continue
        finish_query_list.append(query)
    print(bad_query_list)

#### query -> 爬取相关用户
def search_user_from_query(browser, query_list, finish_query_list):
    '''
    根据query采集maxsize用户列表
    '''
    for query in tqdm(query_list):
        logger.info('query = {}'.format(query))
        browser.get('https://twitter.com/explore')

        # 定位搜索框
        if browser.current_url == 'https://twitter.com/explore':
            search_input = get_search_input_v1(browser)
        else:
            print('error')
            return
        # 搜索query
        search_input.clear()
        search_input.send_keys(query)
        search_input.send_keys(Keys.ENTER)

        # 获取结果
        if is_non_result(browser):
            bad_query_list.append(query)
            continue
        time.sleep(2)
        # 请求用户结果页面
        browser.get(browser.current_url + '&f=user')

        try:
            crawl_user(browser, query)
        except TimeoutException as e:
            print('TimeoutException')
            continue
        finish_query_list.append(query)

    print(bad_query_list)


def parse_user_result_div(result_div, query):
    count = 0
    for t in result_div:
        left, right = t.find_elements_by_xpath('./div/div')
        profile_url = left.find_element_by_tag_name(
            'a').get_attribute('href').strip()
        uid = profile_url.split('/')[-1]
        print('parsing uid = {}'.format(uid))
        avatar = left.find_element_by_tag_name('img').get_attribute('src')
        a, *b = right.find_elements_by_xpath('./div')  # 按照div分为>=3层
        uname = a.text.split('\n')[0]
        intro = ''
        if len(b) != 0:
            intro = b[-1].text.strip()

        user = User(profile_url)
        user.ID = uid
        user.avatar = avatar
        user.name = uname
        user.intro = intro
        user.query = query

        user_dict = user.__dict__
        user_dict['_id'] = user_dict['ID']

        # save to databse
        if user_table.update_one({'_id': user_dict['_id']}, {'$set': user_dict}, upsert=True):
            count += 1
    return count


def crawl_user(browser, query):
    count = 0
    result_div_xpath = '//div[@data-testid="UserCell"]'
    wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
    result_div = browser.find_elements_by_xpath(result_div_xpath)
    last_div = result_div[-1]
    count += parse_user_result_div(result_div, query)

    while count < MAX_USER_SIZE:
        #         logger.info("{}/{}".format(count,MAX_USER_SIZE))
        wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
        result_div = browser.find_elements_by_xpath(result_div_xpath)
        last_div = result_div[-1]

        try:
            count += parse_user_result_div(result_div, query)
            time.sleep(2)
        except StaleElementReferenceException as e:
            time.sleep(2)
            continue

        # 翻页
        try_times = 0
        old_height = browser.execute_script("return document.body.scrollHeight;")
        while True:
            browser.execute_script(
                'window.scrollTo(0,document.body.scrollHeight)')
            wait.until(EC.presence_of_element_located(
                (By.XPATH, result_div_xpath)))
            result_div = browser.find_elements_by_xpath(result_div_xpath)
            if result_div[-1] == last_div:
                try_times += 1
            if result_div[-1] != last_div:
                last_div = result_div[-1]
                break
            time.sleep(3)
            new_height = browser.execute_script("return document.body.scrollHeight;")
            if old_height == new_height:
                try_times += 1
                last_div = result_div[-1]
            if try_times >= 3:
                count = MAX_TWEET_SIZE  # 到头了停止翻页采集该query
                print('到头了')
                break

#### 爬取特定用户的推文（时间间隔内）
def search_tweet_from_profile_v2(browser, query_user_list, finish_user_list):
    for u in tqdm(query_user_list):
        logger.info('user = {}'.format(u['_id']))
        user_profile = 'https://twitter.com/' + u['_id']
        browser.get(user_profile)
        query = u['query']

        # 获取结果
        if is_non_result(browser):
            bad_query_list.append(query)
            continue
        time.sleep(1)
        try:
            crawl_tweet2(browser, query)
        except TimeoutException as e:
            print('TimeoutException')
            continue

        finish_user_list.append(user)
    print(bad_query_list)


def crawl_tweet2(browser, query):
    count = 0
    result_div_xpath = '//div[@data-testid="tweet"]'
    wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
    result_div = browser.find_elements_by_xpath(result_div_xpath)
    last_div = result_div[-1]
    # 解析结果
    count += parse_tweet_from_profile(result_div, query)
    while count < MAX_TWEET_SIZE:
        #         logger.info("{}/{}".format(count,MAX_TWEET_SIZE))
        result_div_xpath = '//div[@data-testid="tweet"]'
        wait.until(EC.presence_of_element_located((By.XPATH, result_div_xpath)))
        result_div = browser.find_elements_by_xpath(result_div_xpath)
        last_div = result_div[-1]
        try:
            count += parse_tweet_from_profile(result_div, query)
        except StaleElementReferenceException as e:
            time.sleep(2)
            continue

        # 翻页
        try_times = 0
        old_height = browser.execute_script("return document.body.scrollHeight;")
        while True:
            browser.execute_script(
                'window.scrollTo(0,document.body.scrollHeight)')
            wait.until(EC.presence_of_element_located(
                (By.XPATH, result_div_xpath)))
            result_div = browser.find_elements_by_xpath(result_div_xpath)
            if result_div[-1] == last_div:
                try_times += 1
            if result_div[-1] != last_div:
                last_div = result_div[-1]
                break
            time.sleep(3)
            new_height = browser.execute_script("return document.body.scrollHeight;")
            if old_height == new_height:
                try_times += 1
                last_div = result_div[-1]
            if try_times >= 3:
                count = MAX_TWEET_SIZE  # 到头了停止翻页采集该query
                print('到头了')
                break


def parse_tweet_from_profile(result_div, query):
    count = 0
    top = 0  # 置顶是个数目
    # 如果存在置顶推文则不考虑时间
    try:
        t = browser.find_elements_by_xpath('//div[@class="css-1dbjc4n r-1habvwh r-1iusvr4 r-16y2uox r-5f2r5o"]')
        top = len(t)
    except NoSuchElementException as e:
        pass

    for div in result_div:
        user, tweet = div.find_elements_by_xpath('./div')
        profile_url = user.find_element_by_tag_name(
            'a').get_attribute('href').strip()
        uid = profile_url.split('/')[-1]
        a, *b_c, d = tweet.find_elements_by_xpath('./div')  # 按照div分为>=3层
        ptime = a.find_elements_by_tag_name('a')[-1].text
        ptime = convert_time(ptime)

        # 无置顶推文则按照时间过滤
        top -= 1
        if top < 0 and compare_time(ptime, time_interval) < 0:
            print('触发时间截止')
            return MAX_TWEET_SIZE  # 使其直接达到数目规模，从而停止外层循环

        nb_reply, nb_retweet, nb_favorite = 0, 0, 0
        try:
            nb_reply, nb_retweet, nb_favorite = extract_reply_retweet_favorite(
                d)
        except:
            nb_reply, nb_retweet, nb_favorite = 0, 0, 0
        pcontent = b_c[0].text
        padditional = []
        if len(b_c) > 1:
            for x in b_c[1:]:
                try:
                    a = x.find_element_by_tag_name('a').get_attribute('href')
                    padditional.append(a)
                except NoSuchElementException as e:
                    padditional.append(x.text.strip())
        tweet = Tweet(query, uid, ptime, pcontent, padditional,
                      nb_reply, nb_retweet, nb_favorite)

        if tweet2_table.insert_one(tweet.__dict__):
            count += 1
    return count

#### 启动浏览器并登陆
client = pymongo.MongoClient("mongodb://localhost:27017/")
twitter_db = client["twitter_v2"]
user_table = twitter_db['user']
tweet_table = twitter_db['tweet_by_query']
tweet2_table = twitter_db['tweet_by_user']

# 打开浏览器
browser = webdriver.Chrome()
wait = WebDriverWait(browser, 100)

# 人工登录
browser.get('https://twitter.com/')

browser.refresh()
time.sleep(2)

import pandas as pd

# df = pd.read_csv('./projects.csv',encoding='utf-8')
# df.columns = ['Project','Country','Type']
# query_list = [x.strip() for x in df['Project'].tolist() if len(x.split()) <= 5]
# query_list = query_list
query_list = ['pp krit','tylor swift']
# df = pd.read_csv('./policies.csv',encoding='utf-8')
# df.columns = ['P','_','__']
# query_list = [x.strip() for x in df['P'].tolist() if len(x.split()) <= 10]
# query_list = query_list
len(query_list)

#%%

# 第1步
finish_query_list = []
bad_query_list = []
MAX_TWEET_SIZE = 1000
search_tweet_from_query(browser,query_list,finish_query_list)

# 第2步
# MAX_TWEET_SIZE = 1000
# special_list = [
#     "the belt and road",
#     'One Belt one road',
#     "the Silk Road",
#     'the Silk Road Economic Belt',
#     'Belt and Road Initiative',
#     '21st Century Maritime Silk Road',
#     'Spirit of the Silk Road',
#     'Silk Road Fund',
#     'Silk Road of Green Development'
# ]
# search_tweet_from_query(browser,special_list,finish_query_list)

len(finish_query_list)

browser.refresh()
time.sleep(4)

##### 采集用户

finish_query_list = []
bad_query_list = []
MAX_USER_SIZE = 50
special_list = [
    "belt and road",
    "One Belt one road",
    'Belt and Road Initiative'
]
search_user_from_query(browser,special_list,finish_query_list)

##### 采集用户主页推文

finish_user_list = []
bad_query_list = []

query_user_list = [u for u in user_table.find() if u['query']!='']# query 不为空的user

print(len(query_user_list))

MAX_TWEET_SIZE = 1000
time_interval = "20120年10月20日" # 默认截止到今日
search_tweet_from_profile_v2(browser,query_user_list,finish_user_list)
