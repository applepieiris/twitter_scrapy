# TwitterSpider
Twitter Spider 推特爬虫，支持搜索关键词采集推文数据，采集相关用户，采集用户主页推文

# parse_twitter_by_query
原先的代码有点问题，在parse_twitter_by_query.py中我修改了部分代码，可以实现从twitter的搜索框根据关键词进行搜索，将结果保存下来。结果分为两部分：1、TOP标签下的twitter文本 2、Latest标签下的文本。原代码将爬虫结果存储在MongoDB中，本代码增加了写入json文件的操作.

# requirements:
selenium

