HOST=$1
DEVICE=$2
TIME=$(date -u +%s)
DATA="{\"time\":$TIME}"
echo host=$HOST device=$DEVICE time=$TIME data=$DATA
curl -i -X POST http://$HOST/api/event/$DEVICE -H "Content-Type: application/json" --data $DATA