
# Maharani Purchase Manager - MongoDB Atlas Version

## Architecture
Phone 1 / Phone 2 / Office Computer -> Render Free Web Service -> MongoDB Atlas

## MongoDB Atlas
Create a FREE M0 cluster, create a database user, and copy the connection string.

Set these Render environment variables:
- MONGODB_URI
- MONGODB_DB=maharani_purchase

Example:
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority

## Images
Product images and mobile camera photos are stored in MongoDB GridFS inside the same Atlas database.

## Local run
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt

Then set:
export MONGODB_URI='YOUR_ATLAS_CONNECTION_STRING'
export MONGODB_DB='maharani_purchase'

Run:
python3 -m flask --app app run --debug --port 5002

Open:
http://127.0.0.1:5002

Health check:
http://127.0.0.1:5002/api/health

## GitHub
Replace your existing project files with these files while keeping `.git`, then:

git add .
git commit -m "Switch purchase manager to MongoDB Atlas"
git push origin main


## Separate Product Photo Storage (Cloudinary)

This version stores purchase/product data in MongoDB Atlas and new product photos in Cloudinary.

### Render environment variables

Keep:
- `MONGODB_URI`
- `MONGODB_DB=maharani_purchase`

Add:
- `CLOUDINARY_URL`

Get `CLOUDINARY_URL` from your Cloudinary account dashboard/API keys.

### Existing photos

Existing MongoDB GridFS photos remain readable. New photos are uploaded to Cloudinary.
Deleting a purchase also attempts to delete its Cloudinary image.

### Image optimization

Common JPG/PNG/WEBP phone photos are resized to a maximum 1800px side and converted to optimized JPEG before upload.
HEIC is sent directly to Cloudinary.

### Security

Do not commit `.env` or real credentials to Git.
