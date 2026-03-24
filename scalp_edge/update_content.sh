#!/bin/bash
# Bruk: bash update_content.sh
# Oppdaterer tekst på nettsiden via Flask-serveren
#
# Krever at SCALP_API_KEY er satt som miljøvariabel:
#   export SCALP_API_KEY="din-nøkkel"

curl -s -X POST http://localhost:5000/update-content \
     -H "X-API-Key: $SCALP_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "updates": [
         {
           "file": "index.html",
           "selector": "#hero-title",
           "content": "Oppdatert overskrift"
         }
       ],
       "commit_message": "Automatisk tekstoppdatering"
     }' | python3 -m json.tool
