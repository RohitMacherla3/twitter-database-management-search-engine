# Import Libraries
from flask import Flask, redirect, url_for, render_template, request
import pymongo
import json
import time
from datetime import datetime
import mysql.connector as cnx
import pickle
from nltk.corpus import stopwords
import os


# connect to mysql server
mydb = cnx.connect(
  host="localhost",
  user="root",
  password="Anirudh13",
  database="mydatabase"
)

mycursor = mydb.cursor(buffered=True)

#connect to mongodb
client = pymongo.MongoClient("mongodb://localhost:27017/") 
db = client["Tweets_DB"]
tweets_collec = db["Tweets_data"]


class Cache:
    def __init__(self, max_size=15000, evict_strategy='least_accessed', checkpoint_interval=30, ttl=None):
        self.max_size = max_size
        self.evict_strategy = evict_strategy
        self.checkpoint_interval = checkpoint_interval
        self.ttl = ttl
        self.cache = {}
        self.access_count = {}
        self.last_checkpoint = time.time()
    
        if os.path.exists('cache.checkpoint'):
            self.load_from_checkpoint('cache.checkpoint')

    def load_from_checkpoint(self, checkpoint_file):
        with open(checkpoint_file, 'rb') as f:
            self.cache, self.access_count = pickle.load(f)

    def save_to_checkpoint(self, checkpoint_file):
        with open(checkpoint_file, 'wb') as f:
            pickle.dump((self.cache, self.access_count), f)
            
    def get(self, key):
        
        if key[0].isdigit() or key.startswith('#'):
            if key not in self.cache:
                return None
            similar_keys = [key]
            
        else:
            similar_keys = []
            for k in self.cache:
                if key in k:
                    similar_keys.append(k)

            if len(similar_keys) == 0:
                return None
        
        if self.ttl is not None and (time.time() - self.cache[key]['timestamp']) > self.ttl:
            del self.cache[key]
            del self.access_count[key]
            return None
        
        for i in similar_keys:
            self.access_count[i] += 1
            
            if self.evict_strategy == 'least_accessed':
                least_accessed_key = min(self.access_count, key=self.access_count.get)
                if len(self.cache) > self.max_size and key != least_accessed_key:
                    del self.cache[least_accessed_key]
                    del self.access_count[least_accessed_key]
                
        return [self.cache[k]['value'] for k in similar_keys]

    def put(self, key, value):
        if not key.startswith('#'):
            key = key.lower()
        self.cache[key] = {'value': value, 'timestamp': time.time()}
        self.access_count[key] = 0
        if len(self.cache) > self.max_size:
            if self.evict_strategy == 'least_accessed':
                least_accessed_key = min(self.access_count, key=self.access_count.get)
                del self.cache[least_accessed_key]
                del self.access_count[least_accessed_key]
            elif self.evict_strategy == 'oldest':
                oldest_key = min(self.cache, key=lambda k: self.cache[k]['timestamp'])
                del self.cache[oldest_key]
                del self.access_count[oldest_key]
                
        if (time.time() - self.last_checkpoint) > self.checkpoint_interval:
            self.save_to_checkpoint('cache.checkpoint')
            self.last_checkpoint = time.time()
            
    def print_cache(self):
        print('Cache:')
        for key, value in self.cache.items():
            print(f"{key}")
        used_space = len(self.cache)
        remaining_space = self.max_size - used_space
        print(f"Cache size: {used_space}")
        print(f"Remaining space: {remaining_space}")


cache = Cache()

# check if the search term starts with '@'
def UserSearch(search_term):
    
    if search_term.startswith('@'):
    # remove the '@' symbol from the search term
        search_term = search_term[1:]
        
        if cache.get(search_term):
            results = cache.get(search_term)
            
        else:
            # execute the query to search for user details based on username
            query = """
                SELECT * FROM users 
                WHERE name LIKE %s 
                ORDER BY followers_count DESC, tweets_count DESC, verified DESC
                LIMIT 5
                """
            mycursor.execute(query, ('%' + search_term + '%',))
            results = mycursor.fetchall()
            for i in range(0,len(results)):
                cache.put(results[i][1], results[i])

        return results
    

def get_user_tweets(user_id):
    
    if cache.get(user_id):
        tweet_details = cache.get(user_id)
    
    else:
        
        user_tweets = list(tweets_collec.find({'User_Id': user_id}).sort([('created_at', -1)]).limit(3))
        tweet_details = []
        
        for tweet in user_tweets:
            tweet_details.append({
                'created_at': tweet['created_at'],
                'text': tweet['Text'],
                'hashtags': tweet['Hashtag'],
                'retweet_count': tweet['Retweet_Count'],
                'likes_count': tweet['Likes_Count']
            })
        
        cache.put(user_id, tweet_details)
    return tweet_details


def get_top_hashtags(search_string, limit=5):
    
    if search_string.startswith('#'):
        search_string = search_string[1:]
        
        hashtags = tweets_collec.aggregate([
        { "$match": { "Hashtag": { "$regex": search_string, "$options": "i" } } },
        { "$unwind": "$Hashtag" },
        { "$group": { "_id": "$Hashtag", "count": { "$sum": 1 } } },
        { "$sort": { "count": -1 } },
        { "$limit": limit }
        ])
        
        hashtag_dict = {}
        for hashtag in hashtags:
            hashtag_dict[hashtag['_id']] = hashtag['count']
            
        return hashtag_dict


def tweets_of_hashtag(hashtag):
    
    if cache.get('#' + hashtag):
        tweets = cache.get(hashtag)[0]
    else:
        tweets = list(tweets_collec.find({'Hashtag': hashtag}).sort('created_at', -1).limit(3))
        cache.put('#' + hashtag, tweets)
    
    return tweets


tweets_collec.create_index([("Text", "text")])

def search_tweets(search_string):

    stop_words = set(stopwords.words('english'))
    search_words = search_string.split()
    if len(set(search_words) - stop_words) == 0:
        return "Error"
    
    search_string = '"' + search_string + '"'
    # Search for tweets matching the search string
    query = {'$text': {'$search': search_string}}
    projection = {'_id': 0, 'Text': 1, 'ext': 1, 'created_at': 1, 'Retweet_Count': 1, 'favorite_count': 1, 'Hashtags': 1}
    matching_tweets = list(tweets_collec.find(query).sort([('retweeted_status', 1), ('created_at', -1)]).limit(5))

    return matching_tweets


# Top 10 hashtags with are present in most tweets
def get_top_10_hashtags(limit=10):
    pipeline = [
        {"$unwind": "$Hashtag"},
        {"$group": {"_id": "$Hashtag", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]
    top_hashtags = list(tweets_collec.aggregate(pipeline))
    top_hashtags_dict = {}
    for hashtag in top_hashtags:
        top_hashtags_dict[hashtag['_id']] = hashtag['count']
    return top_hashtags_dict

top_10_hash= get_top_10_hashtags()

# Top 10 Tweets with most a composite score of Retweets*0.6 + Likes*0.4
def get_top_tweets():
    tweets = tweets_collec.find().sort([("Retweet_Count", -1), ("Likes_Count", -1)]).limit(10)
    top_tweets = []
    for tweet in tweets:
        score = tweet['Retweet_Count'] * 0.6 + tweet['Likes_Count'] * 0.4
        tweet['score'] = score
        top_tweets.append(tweet)
    top_tweets = sorted(top_tweets, key=lambda x: x['score'], reverse=True)
    return top_tweets

top_10_tweets= get_top_tweets()


 # Top 10 users with most followers, tweets
query = """select id,name,screen_name,verified,followers_count,friends_count,location,tweets_count,Description from mydatabase.users 
 order by followers_count DESC,tweets_count DESC 
 limit 10"""

mycursor.execute(query)
top_10_users = mycursor.fetchall()

tweets_cache={}

app= Flask(__name__)


@app.route('/')
def welcome():
    return render_template('index.html')

@app.route('/submit', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        global results
        search_term= request.form['input-field']
        if(search_term.startswith("@")):
            results=UserSearch(search_term)
            for result in results[:5]:
                user_id = result[0]
                tweets_cache[user_id] = get_user_tweets(user_id)
            return render_template('username.html', username=search_term, userinfo=results[:5])
        elif(search_term.startswith("#")):
            hashtags = get_top_hashtags(search_term)
            global temp_hashtag
            temp_hashtag={}
            for hashtag in hashtags.keys():
                temp_hashtag[hashtag] = tweets_of_hashtag(hashtag)
            
            return render_template('hashtag.html', hashtag_name=search_term, hashtag_info=hashtags)
        
        else:
            string_match_tweets= search_tweets(search_term)
            return render_template('strings.html', string_search=search_term, string_tweets=string_match_tweets)
        

@app.route('/submit_top', methods=['GET', 'POST'])
def top_10():
    if request.method == 'POST':
        if request.form['action'] == 'Trending Users':
            return render_template('top_users.html',accounts=top_10_users)
        elif request.form['action'] == 'Trending Tweets':
            return render_template('top_tweets.html', string_tweets=top_10_tweets)
        elif request.form['action'] == 'Trending Hashtags':
            return render_template('top_hashtags.html', hashtag_info=top_10_hash)
        else:
            message = ''
        
    return render_template('top.html', message=message)

            
            
    
@app.route('/submit2', methods=['GET', 'POST'])
def user_result():
    if request.method == 'POST':
        user_choice= int(request.form['input-field'])
        user_id = results[user_choice-1][0]
        if user_id in tweets_cache:
            tweet=tweets_cache[user_id]
        else:
            tweet=['1','2','3']
        user_id=results[user_choice-1][1]
        return render_template('username_tweets.html',username=user_id,tweets=tweet)
    
@app.route('/submit3', methods=['GET', 'POST'])
def hash_result():
    if request.method == 'POST':
        hashtag_select= str(request.form['input-field'])
        return render_template('hashtag_tweets.html',hashtag_choice=hashtag_select,hash_cache=temp_hashtag)


if __name__== '__main__':
    app.run(debug=True)

