from flask import Flask, redirect, url_for, render_template, request

app= Flask(__name__)

@app.route('/')
def welcome():
    return render_template('index.html')

@app.route('/submit', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        input_text = request.form['input-field']
        if input_text.startswith('@'):
            return redirect(url_for('username', username=input_text))
        elif input_text.startswith('#'):
            return redirect(url_for('hashtag', hashtag=input_text))
        else:
            # do something else if not username or hashtag
            pass
    return render_template('index.html')

@app.route('/username/<username>')
def username(username):
    return render_template('username.html', username=username)

@app.route('/hashtag/<hashtag>')
def hashtag(hashtag):
    return render_template('hashtag.html', hashtag=hashtag)



if __name__== '__main__':
    app.run(debug=True)

