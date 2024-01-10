import re
import json
import praw

from . import constants
from . import db
from . import ai
from . import utils

# https://www.reddit.com/prefs/apps
reddit = praw.Reddit(
    username=constants.REDDIT_USERNAME,
    password=constants.REDDIT_PASSWORD,
    client_id=constants.REDDIT_CLIENT_ID,
    client_secret=constants.REDDIT_CLIENT_SECRET,
    user_agent=constants.REDDIT_USER_AGENT
)


def search_posts(keyword: str, latest_post_timestamp):
    posts = []

    # https://www.reddit.com/dev/api/#GET_search
    # https://praw.readthedocs.io/en/stable/code_overview/models/subreddit.html#praw.models.Subreddit.search
    try:
        for post in reddit.subreddit('all').search(
                f'"{keyword}"', sort='relevance', time_filter='year', limit=100
        ):
            contains_keyword = keyword in post.title or keyword in post.selftext

            if contains_keyword and not post.over_18:
                if not latest_post_timestamp or (post.created_utc > latest_post_timestamp):
                    posts.append({
                        'post_id': post.id,
                        'title': post.title,
                        'text': post.selftext,
                        'link': f'https://www.reddit.com{post.permalink}',
                        'created_at': post.created_utc,
                    })
    except Exception:
        return posts

    return posts


def get_models_posts(existed_models):
    posts = {}

    for model in existed_models:
        try:
            repo_id = model['repo_id']

            with db.connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT UNIX_TIMESTAMP(created_at) FROM {constants.MODEL_REDDIT_POSTS_TABLE_NAME}
                    WHERE model_repo_id = '{repo_id}'
                    ORDER BY created_at DESC
                    LIMIT 1
                """)

                latest_post_timestamp = cursor.fetchone()
                latest_post_timestamp = float(latest_post_timestamp[0]) if latest_post_timestamp != None else None

            keyword = model['name'] if re.search(r'\d', model['name']) else repo_id
            found_posts = search_posts(keyword, latest_post_timestamp)

            if not len(found_posts):
                continue

            posts[repo_id] = found_posts
        except Exception as e:
            print(e)
            continue

    return posts


def insert_models_posts(posts):
    if not len(posts):
        return

    for model_repo_id, posts in posts.items():
        if not len(posts):
            continue

        for post in posts:
            try:
                values = []

                value = {
                    'model_repo_id': model_repo_id,
                    'post_id': post['post_id'],
                    'title': post['title'],
                    'clean_text': utils.clean_string(post['text']),
                    'link': post['link'],
                    'created_at': post['created_at'],
                }

                to_embedding = {
                    'model_repo_id': model_repo_id,
                    'title': value['title'],
                    'clean_text': value['clean_text']
                }

                if ai.count_tokens(value['clean_text']) <= constants.TOKENS_TRASHHOLD_LIMIT:
                    embedding = str(ai.create_embedding(json.dumps(to_embedding)))
                    values.append({**value, 'embedding': embedding})
                else:
                    for chunk in utils.string_into_chunks(value['clean_text']):
                        embedding = str(ai.create_embedding(json.dumps({
                            **to_embedding,
                            'clean_text': chunk
                        })))
                        values.append({**value, 'clean_text': chunk, 'embedding': embedding})

                for chunk in utils.list_into_chunks([list(value.values()) for value in values]):
                    with db.connection.cursor() as cursor:

                        cursor.executemany(f'''
                            INSERT INTO {constants.MODEL_REDDIT_POSTS_TABLE_NAME} (model_repo_id, post_id, title, clean_text, link, created_at, embedding)
                            VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), JSON_ARRAY_PACK(%s))
                        ''', chunk)
            except Exception as e:
                print(e)
                continue
