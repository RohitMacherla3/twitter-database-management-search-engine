from flask import Flask

app= Flask(__name__)

@app.route('/')
def welcome():
    return "Welcome to this page"

@app.route('/members')
def members():
    return "Welcome to this page peeps"


if __name__== '__main__':
    app.run(debug=True)

