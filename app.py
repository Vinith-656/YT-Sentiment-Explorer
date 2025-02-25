from flask import Flask, render_template, request, send_file, jsonify
from googleapiclient.discovery import build
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import pandas as pd
import matplotlib.pyplot as plt
import re

app = Flask(__name__)

# Initialize YouTube API
API_KEY = 'YOUR_API_KEY'
youtube = build('youtube', 'v3', developerKey=API_KEY)

# Function to extract video ID from URL
def extract_video_id(url):
    regex = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(regex, url)
    return match.group(1) if match else None

# Function to fetch total comments count
def get_total_comments(video_id):
    try:
        response = youtube.videos().list(
            part="statistics",
            id=video_id
        ).execute()
        
        if "items" in response and response["items"]:
            return int(response["items"][0]["statistics"].get("commentCount", 0))
    except Exception as e:
        print(f"Error fetching comment count: {e}")
    return 0

# Function to fetch comments
def fetch_comments(video_id, max_results):
    comments = []
    next_page_token = None
    results_fetched = 0

    try:
        while results_fetched < max_results:
            response = youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                textFormat='plainText',
                maxResults=min(100, max_results - results_fetched),  # Fetch in batches of 100
                pageToken=next_page_token
            ).execute()

            if 'items' not in response:
                break  # Stop if no more items

            for item in response['items']:
                top_comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(top_comment)
                results_fetched += 1
                if results_fetched >= max_results:
                    break

                # Fetch replies if available
                reply_count = item['snippet']['totalReplyCount']
                if reply_count > 0:
                    parent_id = item['snippet']['topLevelComment']['id']
                    replies = fetch_replies(video_id, parent_id, max_results - results_fetched)
                    comments.extend(replies)
                    results_fetched += len(replies)
                    if results_fetched >= max_results:
                        break

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break  # No more pages

            print(f"Fetched {results_fetched} comments (including replies)...")  # Debugging print

    except Exception as e:
        print(f"An error occurred: {e}")

    return comments


# function to fetch replies
def fetch_replies(video_id, parent_id, max_results):
    replies = []
    next_page_token = None

    try:
        while len(replies) < max_results:
            response = youtube.comments().list(
                part='snippet',
                videoId=video_id,
                parentId=parent_id,
                textFormat='plainText',
                maxResults=min(50, max_results - len(replies)),  # Replies are limited to 50 per request
                pageToken=next_page_token
            ).execute()

            if 'items' not in response:
                break

            for item in response['items']:
                reply = item['snippet']['textDisplay']
                replies.append(reply)
                if len(replies) >= max_results:
                    break  # Stop if we reach the limit

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break  # No more replies

    except Exception as e:
        print(f"Error fetching replies: {e}")

    return replies


# Function to analyze sentiment
def analyze_sentiment(comments):
    analyzer = SentimentIntensityAnalyzer()
    results = {'Neutral': [], 'Negative': [], 'Positive': []}

    for comment in comments:
        score = analyzer.polarity_scores(comment)['compound']
        if score >= 0.05:
            results['Positive'].append(comment)
        elif score <= -0.05:
            results['Negative'].append(comment)
        else:
            results['Neutral'].append(comment)
    return results

# Function to calculate accuracy
def calculate_accuracy(results, total_comments):
    total_positive = len(results['Positive'])
    total_negative = len(results['Negative'])
    correct_predictions = total_positive + total_negative  
    accuracy = (correct_predictions / total_comments) * 100 if total_comments > 0 else 0
    return round(accuracy, 2)

# Function to create pie chart
def create_pie_chart(results, filename):
    labels = results.keys()
    sizes = [len(results[label]) for label in labels]
    plt.figure(figsize=(5,3))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.axis('equal')
    plt.savefig(filename)
    plt.close()

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        video_url = request.form['video_url']
        video_id = extract_video_id(video_url)
        
        if not video_id:
            return render_template('ind.html', error="Invalid YouTube URL")

        max_results = int(request.form['max_results'])
        csv_filename = request.form['csv_filename']

        comments = fetch_comments(video_id, max_results)
        results = analyze_sentiment(comments)
        accuracy = calculate_accuracy(results, len(comments))

        # Save results to CSV
        df = pd.DataFrame({
            'Comment': comments,
            'Sentiment': ['Positive' if comment in results['Positive'] else 'Negative' if comment in results['Negative'] else 'Neutral' for comment in comments]
        })
        df.to_csv(csv_filename, index=False)

        # Create pie chart
        pie_chart_filename = 'sentiment_distribution.jpg'
        create_pie_chart(results, pie_chart_filename)

        return render_template('res.html', total_comments=len(comments), accuracy=accuracy, results=results, video_url=video_url)

    return render_template('ind.html')

@app.route('/get_total_comments', methods=['POST'])
def total_comments():
    video_url = request.json.get('video_url')
    video_id = extract_video_id(video_url)

    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    total_comments = get_total_comments(video_id)
    return jsonify({'total_comments': total_comments})

@app.route('/<filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
