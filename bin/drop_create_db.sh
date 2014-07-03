#!/bin/bash
# drops the ``seed`` DB, then creates it. Add a super_user
# demo@buidlingenergy.com with password demo

dropdb seed
createdb seed
python manage.py syncdb --migrate
echo "from landing.models import SEEDUser as User; User.objects.create_superuser('demo@buildingenergy.com', 'demo@buildingenergy.com', 'demo')" | ./manage.py shell