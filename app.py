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



get_top_10_users= [('813286',
   'Barack Obama',
   'BarackObama',
   1,
   116518121,
   607194,
   'Washington, DC',
   1,
   'Dad, husband, President, citizen.'),
  ('25073877',
   'Donald J. Trump',
   'realDonaldTrump',
   1,
   78467254,
   46,
   'Washington, DC',
   0,
   '45th President of the United States of America🇺🇸'),
  ('428333',
   'CNN Breaking News',
   'cnnbrk',
   1,
   57529057,
   120,
   'Everywhere',
   0,
   'Breaking news from CNN Digital. Now 56M strong. Check @cnn for all things CNN, breaking and more. Download the app for custom alerts: http://cnn.com/apps'),
  ('18839785',
   'Narendra Modi',
   'narendramodi',
   1,
   55781248,
   2364,
   'India',
   6,
   'Prime Minister of India'),
  ('44409004',
   'Shakira',
   'shakira',
   1,
   52250613,
   212,
   'Barranquilla',
   0,
   '🎙ME GUSTA Shakira & Anuel AA Nuevo Sencillo / New Single'),
  ('759251',
   'CNN',
   'CNN',
   1,
   47567385,
   1106,
   None,
   0,
   'It’s our job to #GoThere & tell the most difficult stories. Join us! For more breaking news updates follow @CNNBRK  & Download our app http://cnn.com/apps'),
  ('807095',
   'The New York Times',
   'nytimes',
   1,
   46359985,
   904,
   'New York City',
   1,
   'News tips? Share them here: http://nyti.ms/2FVHq9v'),
  ('5402612',
   'BBC Breaking News',
   'BBCBreaking',
   1,
   43014510,
   3,
   'London, UK',
   0,
   'Breaking news alerts and updates from the BBC. For news, features, analysis follow @BBCWorld (international) or @BBCNews (UK). Latest sport news @BBCSport.'),
  ('145125358',
   'Amitabh Bachchan',
   'SrBachchan',
   1,
   41596464,
   1833,
   'Mumbai, India',
   1,
   '"तुमने हमें पूज पूज कर पत्थर कर डाला ; वे जो हमपर जुमले कसते हैं हमें ज़िंदा तो समझते हैं "~  हरिवंश राय  बच्चन'),
  ('132385468',
   'Salman Khan',
   'BeingSalmanKhan',
   1,
   40094611,
   26,
   'MUMBAI',
   0,
   'Film actor, artist, painter, humanitarian')]

get_top_10_hashtags={'Corona': 5920,
  'corona': 1928,
  'Mattarella': 1516,
  '25Aprile': 1476,
  'Covid_19': 1119,
  'COVID19': 1003,
  'coronavirus': 825,
  'AltaredellaPatria': 806,
  'Liberazione': 700}

get_top_10_tweets= [{'created_at': '2020-04-25 09:23:42',
   'Tweet_Id': '1253977978620518400',
   'Text': '#25Aprile, il Presidente #Mattarella si è voluto recare all’#AltaredellaPatria dove ha deposto una corona d’alloro… https://t.co/ev4b4DlgDf',
   'Hashtag': ['25Aprile', 'Mattarella', 'AltaredellaPatria'],
   'User_Id': '732819391',
   'User_Name': 'Quirinale',
   'Retweet_Count': 798,
   'Likes_Count': 9524,
   'score': 4288.400000000001},
  {'created_at': '2020-04-25 05:24:38',
   'Tweet_Id': '1253917813791690752',
   'Text': 'Ngomongin teori konspirasi corona sama orang yg percaya kalo bumi itu datar, I’m not a smart people, but please dud… https://t.co/aClWBZg41m',
   'Hashtag': [],
   'User_Id': '31079332',
   'User_Name': 'dr. Shela Putri Sundawa',
   'Retweet_Count': 784,
   'Likes_Count': 5498,
   'score': 2669.6000000000004},
  {'created_at': '2020-04-25 09:56:54',
   'Tweet_Id': '1253986335297359874',
   'Text': '#25Aprile, nel 75° anniversario della #Liberazione il Presidente #Mattarella ha deposto una corona all’Altare della… https://t.co/vDcVcwEMQy',
   'Hashtag': ['25Aprile', 'Liberazione', 'Mattarella'],
   'User_Id': '732819391',
   'User_Name': 'Quirinale',
   'Retweet_Count': 654,
   'Likes_Count': 4062,
   'score': 2017.2000000000003},
  {'created_at': '2020-04-25 11:27:12',
   'Tweet_Id': '1254009056517332998',
   'Text': 'And where is the evidence that Covid 19 is easily spread outdoors?  https://t.co/YPcJXU1uqw',
   'Hashtag': [],
   'User_Id': '112047805',
   'User_Name': 'Brit Hume',
   'Retweet_Count': 1474,
   'Likes_Count': 1831,
   'score': 1616.8000000000002},
  {'created_at': '2020-04-25 11:26:44',
   'Tweet_Id': '1254008941408915456',
   'Text': 'Corona disinfecting in Russia. https://t.co/AEF5ccDmM3',
   'Hashtag': [],
   'User_Id': '2904195838',
   'User_Name': '🇷🇺Only In Russia 🇷🇺',
   'Retweet_Count': 586,
   'Likes_Count': 1352,
   'score': 892.4000000000001},
  {'created_at': '2020-04-23 19:58:13',
   'Tweet_Id': '1253412885444743177',
   'Text': 'Quando eu ligo a televisão e  fica falando só de corona vírus',
   'Hashtag': [],
   'User_Id': '1251310476878852096',
   'User_Name': '♠️į§ąč♣️',
   'Retweet_Count': 445,
   'Likes_Count': 1532,
   'score': 879.8000000000001},
  {'created_at': '2020-04-25 12:51:03',
   'Tweet_Id': '1254030161403674624',
   'Text': 'Milwaukee’s health commissioner has now tied 40 coronavirus infections to the April 7 election. \n\nhttps://t.co/fGIsLKzTkm',
   'Hashtag': [],
   'User_Id': '851211',
   'User_Name': 'Ben Wikler',
   'Source_tweet_Id': 0,
   'Retweet_Count': 986,
   'Likes_Count': 0,
   'score': 591.6},
  {'created_at': '2020-04-25 12:43:26',
   'Tweet_Id': '1254028244166356998',
   'Text': 'Gözün çıksın corona😷 Ülkece asabii olduk 🤷\u200d♀️muhtemel psikoloji ektedir 😂😂😂👇\n\n#PideAlmayaDiyeÇıkıp https://t.co/KoGSbVAMxZ',
   'Hashtag': ['PideAlmayaDiyeÇıkıp'],
   'User_Id': '1540461966',
   'User_Name': 'Funda',
   'Source_tweet_Id': 0,
   'Retweet_Count': 732,
   'Likes_Count': 0,
   'score': 439.2},
  {'created_at': '2020-04-25 13:53:37',
   'Tweet_Id': '1254045905252167681',
   'Text': 'A MUST READ...Coronavirus Restrictions: Government Bears the Burden of Proof Before Denying Freedoms | National Rev… https://t.co/RcaAK9nwDs',
   'Hashtag': [],
   'User_Id': '50769180',
   'User_Name': 'Laura Ingraham',
   'Source_tweet_Id': 0,
   'Retweet_Count': 500,
   'Likes_Count': 0,
   'score': 300.0},
  {'created_at': '2020-04-25 13:01:20',
   'Tweet_Id': '1254032746361417729',
   'Text': 'Thalapathy fans from Sivakasi Helped the Poor Family who are affected by this corona Crisis ! They have supplied th… https://t.co/ozoG6d9Ax8',
   'Hashtag': [],
   'User_Id': '751643287870636032',
   'User_Name': 'Gu Ru Thalaiva',
   'Source_tweet_Id': 0,
   'Retweet_Count': 422,
   'Likes_Count': 0,
   'score': 253.2}]


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
        if request.form['action'] == 'Top 10 Users':
            return render_template('top_users.html',accounts=get_top_10_users)
        elif request.form['action'] == 'Top 10 Tweets':
            return render_template('top_tweets.html', string_tweets=get_top_10_tweets)
        elif request.form['action'] == 'Top 10 Hashtags':
            return render_template('top_hashtags.html', hashtag_info=get_top_10_hashtags)
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

