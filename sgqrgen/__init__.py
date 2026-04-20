from flask import Blueprint

# Define the blueprint
image_gen_bp = Blueprint('sgqrgen', __name__, template_folder='templates', url_prefix='/images')

# Note: do not import routes at package import time to avoid circular imports.
# If you need to register routes, import sgqrgen.routes inside application factory.