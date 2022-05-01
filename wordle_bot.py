import os
import random
import boto3
import collections
from enum import Enum
from PIL import Image, ImageDraw, ImageFont
import tweepy
import json
from datetime import datetime, timedelta
import time
import re
import boto3

class State(Enum):
    INCORRECT_POSITION = 0
    CORRECT_POSITION = 1
    NOT_PRESENT = 2
    EMPTY = 3

colors = {
	State.INCORRECT_POSITION: "\x1b[43;30m",
	State.CORRECT_POSITION: "\x1b[42;30m",
	State.NOT_PRESENT: "\033[00m",
	State.EMPTY: "\033[00m"
}

image_colors = {
	State.INCORRECT_POSITION: "#c9b458",
	State.CORRECT_POSITION: "#6aaa64",
	State.NOT_PRESENT: "#86888a",
	State.EMPTY: "#d3d6da",
}

font = ImageFont.truetype('/var/task/package/fonts/HelveticaNeue Bold.ttf', 50)
letter_font = ImageFont.truetype('/var/task/package/fonts/HelveticaNeue Bold.ttf', 20)

SUCESS_MESSAGE = "{} {}! You got it in {}/6 tries!"
INVALID_MESSAGE = "❌ Invalid guess! Try again"
FAIL_MESSAGE = "Nice Try! Max tries exceeded, the word was {}"
GUESS_MESSAGE = "Guess {}/6:"
messages = {
    1: ["🎯", "GENIUS"],
    2: ["🧠", "MAGNIFICENT"],
    3: ["🔥", "IMPRESSIVE"],
    4: ["🏆", "GREAT"],
    5: ["🏅", "NOT BAD"],
    6: ["🤙", "PHEW"]
}

bot_user_id = "1501031219114516482"
s3 = boto3.client('s3')

def get_word_lists():
	solutions_file = open(os.path.join(os.path.dirname(__file__), "/var/task/package/data/solution_list.txt"), "r")
	solutions = solutions_file.read().splitlines()

	guesses_file = open(os.path.join(os.path.dirname(__file__), "/var/task/package/data/guess_list.txt"), "r")
	guesses = guesses_file.read().splitlines()
	guesses = guesses + solutions

	return solutions,guesses

def random_solution(solutions):
	return random.choice(solutions)

def handle_guesses(guesses, solution):
	output_map = {}
	letter_map = {}
	for guess in guesses:
		states = []
		# store pool of incorrect placements & counts
		pool = collections.Counter(s for s, g in zip(solution, guess) if s != g)

		for solution_char, guess_char in zip(solution, guess):
			if solution_char == guess_char:
				letter_map[guess_char] = State.CORRECT_POSITION
				states.append(State.CORRECT_POSITION)
			elif guess_char in solution and pool[guess_char] > 0:
				if guess_char not in letter_map or letter_map[guess_char] != State.CORRECT_POSITION:
					letter_map[guess_char] = State.INCORRECT_POSITION
				pool[guess_char] -= 1
				states.append(State.INCORRECT_POSITION)
			else:
				if guess_char not in letter_map:
					letter_map[guess_char] = State.NOT_PRESENT
				states.append(State.NOT_PRESENT)
		output_map[guess] = states

	return output_map, letter_map

def output(guesses, output_map, letter_map):
	for guess in guesses:
		string = ""
		for letter, state in zip(guess, output_map[guess]):
			string += colors[state] + " " + letter.upper() + " "
		string += colors[State.NOT_PRESENT]

def draw_image(guesses, output_map, letter_map):
	background = Image.new('RGBA', (700, 850), (255, 255, 255, 255))

	for y, guess in enumerate(guesses):
		for x, letter, state in zip(range(len(guess)), guess, output_map[guess]):
			draw_block(background, x, y, letter, state)

	for y in range(len(guesses), 6):
		for x in range(5):
			draw_block(background, x, y, None, State.EMPTY)

	alphabet = ["qwertyuiop","asdfghjkl","zxcvbnm"]
	for y, row in enumerate(alphabet):
		for x, letter in enumerate(row):
			state = letter_map[letter] if letter in letter_map else State.EMPTY
			draw_letter(background, x, y, letter, state)
			
	return background

def draw_letter(background, x, y, letter, state):
	size = (50, 65)
	spacing = 5
	font.size = 5
	side_spacing = {"x":77, "y":600}

	text_color = "black" if state == State.EMPTY else "white"

	color = image_colors[state]
	x_pos = side_spacing["x"] + (size[0] + spacing)*x
	y_pos = side_spacing["y"] + (size[1] + spacing)*y

	if(y == 1):
		x_pos += (size[0]+spacing)*0.5
	elif y==2:
		x_pos += (size[0]+spacing)*1.5
	block_pos = [x_pos, y_pos, x_pos + size[0], y_pos + size[1]]
	text_pos = (x_pos+size[0]/2,y_pos+size[1]/2)

	ImageDraw.Draw(background).rounded_rectangle(block_pos, fill=color, radius=6)
	ImageDraw.Draw(background).text(text_pos, letter.upper(), font=letter_font, anchor="mm", fill=text_color)

def draw_block(background, x, y, letter, state):
	side_spacing = {"x":130, "y":50}
	spacing = 10
	square_size = 80

	x_pos = side_spacing["x"] + (square_size + spacing)*x
	y_pos = side_spacing["y"] + (square_size + spacing)*y

	block_pos = [x_pos, y_pos, x_pos + square_size, y_pos + square_size]
	text_pos = (x_pos+square_size/2,y_pos+square_size/2)

	color = image_colors[state]

	if(letter):
		ImageDraw.Draw(background).rectangle(block_pos, fill=color)
		ImageDraw.Draw(background).text(text_pos, letter.upper(), font=font, anchor="mm")
	else:
		ImageDraw.Draw(background).rectangle(block_pos, outline=color, width=3)

def get_tweepy_client():
	client = tweepy.Client(
    	consumer_key=os.environ['CONSUMER_KEY'],
    	consumer_secret=os.environ['CONSUMER_KEY_SECRET'],
    	access_token=os.environ['ACCESS_TOKEN'],
    	access_token_secret=os.environ['ACCESS_TOKEN_SECRET'],
    	bearer_token=os.environ['BEARER_TOKEN']
	)

	auth = tweepy.OAuth1UserHandler(
	   os.environ['CONSUMER_KEY'], os.environ['CONSUMER_KEY_SECRET'],
	   os.environ['ACCESS_TOKEN'], os.environ['ACCESS_TOKEN_SECRET']
	)
	api = tweepy.API(auth)

	return client, api

def is_start_tweet(tweet, game_sessions):
	if "new game" not in tweet.text.lower():
		return False
	if str(tweet.author_id) not in game_sessions:
		return True
	session = game_sessions[str(tweet.author_id)]
	if session["new_game_id"] == str(tweet.id) or str(tweet.created_at) < session["created_at"]:
		return False

	return True

def is_guess_tweet(tweet, game_sessions):
	if str(tweet.author_id) not in game_sessions:
		return False
	session = game_sessions[str(tweet.author_id)]
	if(tweet.referenced_tweets is None):
		return False
	if(len(re.sub(r"(?:\@|https?\://)\S+", "", tweet.text).strip()) > 7):
		return False
	if(len(session["guesses"]) >= 6):
		return False

	is_referenced = False
	for referenced_tweet in tweet.referenced_tweets:
		if str(referenced_tweet.id) == session["latest_reply"]:
			is_referenced = True
	return is_referenced

def start_session(api, tweet, user, solution_list):
	message = "New Wordle game started. Start by replying with your first guess!"
	status = api.update_status(status=f"@{user.username} {message}", in_reply_to_status_id=str(tweet.id))
	session = {
		"author_id": str(tweet.author_id),
		"latest_reply": str(status.id),
		"guesses": [],
		"solution": random_solution(solution_list),
		"new_game_id": str(tweet.id),
		"created_at": str(tweet.created_at)
	}
	return session

def guess_response(api, message, tweet, user, image=None):
	response = None
	if(image):
		filename = f'/tmp/out_{tweet.id}.png'
		image.save(filename)
		response = api.update_status_with_media(status=f"@{user.username} {message}", filename=filename, in_reply_to_status_id=tweet.id)
		if os.path.exists(filename):
  			os.remove(filename)
	else:
		response = api.update_status(status=f"@{user.username} {message}", in_reply_to_status_id=tweet.id)
	return response.id

def get_since_time(delta_hours):
	date = datetime.utcnow()
	date = date - timedelta(hours=delta_hours)
	return date

def get_replies(client):
	query = f"-is:retweet (to:{bot_user_id} OR @wordle_io)"
	since_date = get_since_time(0.3)

	tweets = []
	users = {}
	for response in tweepy.Paginator(client.search_recent_tweets, query=query, start_time=since_date,
  			expansions=["author_id","referenced_tweets.id"], tweet_fields=["created_at"], user_fields=["username"], max_results=100):
		if not response.data:
			continue
		for user in response.includes['users']:
			users[user.id] = user
		for tweet in response.data:
			tweets.append(tweet)

	return [(tweet, users[tweet.author_id]) for tweet in tweets]

def valid_guess(guess, guess_list):
	return guess in guess_list
	
def get_game_sessions():
	try:
		obj = s3.get_object(
			Bucket=os.environ['S3_BUCKET'], 
			Key=os.environ['GAME_SESSIONS_KEY']
		)
		sessions_json = obj['Body'].read()
		data = json.loads(sessions_json)
		return data
	except Exception as e:
		print("FATAL ERROR: Failed to load sessions: " + str(e))
		exit()

def store_game_sessions(game_sessions):
	sessions_string = json.dumps(game_sessions)
	s3.put_object(
		Bucket=os.environ['S3_BUCKET'],
    	Key=os.environ['GAME_SESSIONS_KEY'],
    	Body=str(sessions_string)
	)

def clear_old_sessions(game_sessions):
	clear_time = str(get_since_time(48))
	for user_id, session in game_sessions.copy().items():
		if(session["created_at"] < clear_time):
			game_sessions.pop(user_id)

def lambda_handler(event, context):
	solution_list, guess_list = get_word_lists()
	client, api = get_tweepy_client()
	game_sessions = get_game_sessions()
	update = False

	tweets = get_replies(client)
	if not tweets: return

	for tweet, user in tweets:

		print(str(tweet.id) + " " + str(user.username) + " " + tweet.text)

		user_id = str(user.id)
		if is_start_tweet(tweet, game_sessions):
			print(" => new game tweet")
			session = start_session(api, tweet, user, solution_list)
			game_sessions[user_id] = session
			update = True
		elif is_guess_tweet(tweet, game_sessions):
			print(" => new guess tweet")
			guess = re.sub(r"(?:\@|https?\://)\S+", "", tweet.text).strip().lower()
			session = game_sessions[user_id]
			update = True
			if len(guess) != 5 or not valid_guess(guess, guess_list):
				tweet_id = guess_response(api, INVALID_MESSAGE, tweet, user)
				session["latest_reply"] = str(tweet_id)
				game_sessions[user_id] = session
				continue

			session["guesses"].append(guess)
			guesses = session["guesses"]

			output_map, letter_map = handle_guesses(guesses, session["solution"])
			image = draw_image(guesses, output_map, letter_map)

			guess_count = len(guesses)
			message = ""
			game_over = False
			if(guess == session["solution"]):
				message = SUCESS_MESSAGE.format(messages[guess_count][0], messages[guess_count][1], guess_count)
				game_over = True
			elif guess_count >= 6:
				message = FAIL_MESSAGE.format(session["solution"])
				game_over = True
			else:
				message = GUESS_MESSAGE.format(guess_count)

			tweet_id = guess_response(api, message, tweet, user, image)
			session["latest_reply"] = str(tweet_id)
			game_sessions[user_id] = session

	if update:
		clear_old_sessions(game_sessions)
		store_game_sessions(game_sessions)
