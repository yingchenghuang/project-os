#!/bin/bash
# encode.sh <framesdir> <out.mp4> <mode: full|even>
set -e
F=$1; OUT=$2; MODE=${3:-full}
if [ "$MODE" = "even" ]; then
  # 12 fps source (even frames) -> motion-interpolated 24 fps
  ls $F/frame_*.jpg | awk -F_ '{n=$NF; sub(".jpg","",n); if (n%2==0) print "file '"'"'"$0"'"'"'"}' > $F/list.txt
  ffmpeg -y -loglevel error -r 12 -f concat -safe 0 -i $F/list.txt -vf "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,format=yuv420p" -c:v libx264 -preset slow -crf 18 -movflags +faststart $OUT
else
  ffmpeg -y -loglevel error -framerate 24 -i $F/frame_%05d.jpg -vf format=yuv420p -c:v libx264 -preset slow -crf 18 -movflags +faststart $OUT
fi
ffprobe -v error -show_entries format=duration,size -of default=nw=1 $OUT
