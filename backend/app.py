import json
import os
from flask import Flask, render_template, request
from flask_cors import CORS
from helpers.MySQLDatabaseHandler import MySQLDatabaseHandler
from dotenv import load_dotenv
import math
from edit_distance import edit_distance_search
import re
import text
import preprocessing
import rocchio

load_dotenv()

# ROOT_PATH for linking with all your files. 
# Feel free to use a config.py or settings.py with a global export variable
os.environ['ROOT_PATH'] = os.path.abspath(os.path.join("..",os.curdir))

# These are the DB credentials for your OWN MySQL
# Don't worry about the deployment credentials, those are fixed
# You can use a different DB name if you want to
MYSQL_USER = "root"
MYSQL_USER_PASSWORD = os.getenv('PASSWORD')
MYSQL_PORT = 3306
MYSQL_DATABASE = "recipesdb"

mysql_engine = MySQLDatabaseHandler(MYSQL_USER,MYSQL_USER_PASSWORD,MYSQL_PORT,MYSQL_DATABASE)

# Path to init.sql file. This file can be replaced with your own file for testing on localhost, but do NOT move the init.sql file
mysql_engine.load_file_into_db()

app = Flask(__name__)
CORS(app)

recipes_data = preprocessing.build_recipes(mysql_engine)
    
ingredients_set = preprocessing.get_all_ingredients(recipes_data)
# Get the list of recipes from the database
recipes_list = preprocessing.build_recipes(mysql_engine)

ingredients_set = preprocessing.get_all_ingredients(recipes_list)

inv_idx = preprocessing.build_inv_idx(recipes_list, ingredients_set)

idf = preprocessing.compute_idf(inv_idx)

def sql_search(ingredient): 
    # Run the SQL query to retrieve matching recipes
    # Get the ingredients from the input
    ingredient_list = [i.strip() for i in ingredient.split(', ')]

    # Assign the importance of each recipe using the idf
    recipe_scores = {}
    for input_ingredient in ingredient_list:
        
        ingredient = input_ingredient
        found = False
        if input_ingredient not in inv_idx:
            # if input_ingredient is not a key in inv_idx, then find the closest ingredient
            # using edit distance, and make ingredient equal to that 
            for key in inv_idx:
                if re.search(r"\b{}\b".format(input_ingredient), key):
                    ingredient = key
                    found = True
                    for recipe_id in inv_idx[ingredient]:
                        recipe_scores[recipe_id] = idf[ingredient] * 0.5 + recipe_scores.get(recipe_id, 0)
                
            if found == False:
                ingredient = edit_distance_search(input_ingredient, ingredients_set)
        
        if found == False:
            for recipe_id in inv_idx[ingredient]:
                recipe_scores[recipe_id] = idf[ingredient] * 2 + recipe_scores.get(recipe_id, 0)
    
    for id in recipe_scores:
        matching_recipe = next((d for d in recipes_list if d["RecipeId"] == id), None)
        rating = matching_recipe["AvgRecipeRating"]
        recipe_scores[id] = recipe_scores[id] * rating
    
    # recipe_scores.items is a tuple list [(recipe id, recipe score)]
    sorted_scores = sorted(recipe_scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for i in range(min(len(sorted_scores), 10)):
        id = sorted_scores[i][0]
        matching_recipe = next((d for d in recipes_list if d["RecipeId"] == id), None)
        ingredient_parts = matching_recipe["RecipeIngredientParts"]
        ingredients = text.remove_c_parantheses(ingredient_parts)
        matching_recipe["RecipeIngredientParts"] = ingredients
        instructions_ = matching_recipe["RecipeInstructions"]
        instructions = text.remove_c_parantheses(instructions_)
        matching_recipe["RecipeInstructions"] = instructions
        results.append(matching_recipe)
    return json.dumps(results)

# Here, we will assign an index for each RecipeId. This index will help us access data in numpy matrices.
recipe_id_to_index = {recipe_id:index for index, recipe_id in enumerate([d['RecipeId'] for d in recipes_data])}

recipe_index_to_id = {index:recipe_id for index, recipe_id in enumerate([d['RecipeId'] for d in recipes_data])}

# We will also need a dictionary mapping recipe ids to ingredients
recipe_id_to_ingredients = {recipeid:ingredients for recipeid, ingredients in zip([d['RecipeId'] for d in recipes_data],
                                                             [d['RecipeIngredientParts'] for d in recipes_data])}

# Here, we will assign an index for each RecipeId. This index will help us access data in numpy matrices.
recipe_name_to_id = {recipe_name:recipe_id for recipe_name, recipe_id in zip([d['Name'] for d in recipes_data],
                                                             [d['RecipeId'] for d in recipes_data])}

# tfidf matrix with X rows (representing recipes) and Y columns (representing ingredients)
tf_idf_matrix = rocchio.tf_idf(recipe_id_to_ingredients)

@app.route("/")
def home():
    return render_template('base.html',title="sample html")

@app.route("/episodes")
def episodes_search():
    text = request.args.get("title")
    return sql_search(text)

@app.route("/recommender")
def update_recommendations():
    liked_titles = request.args.get("likedTitles").split(';')
    disliked_titles = request.args.get("dislikedTitles").split(';')

    results = []

    # get the new recipes here
    # new_recipes is the list of ids of the top 10 recipes
    new_recipes = rocchio.recommend_recipes(liked_titles, disliked_titles, tf_idf_matrix, recipe_id_to_index, recipe_name_to_id, recipe_index_to_id)

    for id in new_recipes:
        matching_recipe = next((d for d in recipes_list if d["RecipeId"] == id), None)
        ingredient_parts = matching_recipe["RecipeIngredientParts"]
        ingredients = text.remove_c_parantheses(ingredient_parts)
        matching_recipe["RecipeIngredientParts"] = ingredients
        instructions_ = matching_recipe["RecipeInstructions"]
        instructions = text.remove_c_parantheses(instructions_)
        matching_recipe["RecipeInstructions"] = instructions
        results.append(matching_recipe)

    return json.dumps(results)

#app.run(debug=True)
