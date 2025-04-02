if [ $1 == "off" ]
then
  wlr-randr --output HDMI-A-1 --off
elif [ $1 == "on" ]
then
  wlr-randr --output HDMI-A-1 --on
else
  wlr-randr
fi
