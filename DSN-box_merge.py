# MERGE 2 .csv Box archive files
import sys
import pandas as pd

if len(sys.argv) > 2:
    box_file= sys.argv[1]
    loc_file= sys.argv[2]
else:
    print('DSN-box_merge: argument missing, 2 .csv files.')
    quit()

# Example usage: python DSN-box_merge.py box1.csv box2.csv

box_df=pd.read_csv(box_file,header=None,skiprows=1,sep=',')
if len(box_df.columns)<8:
    cols_df=['UTC','SQM','lum','chisquared','moonalt','LST','sunalt']
else
    cols_df=['UTC','SQM','lum','chisquared','moonalt','LST','sunalt','Skytemp']
loc_df=pd.read_csv(loc_file,header=None,skiprows=1,sep=',')
box_df=pd.concat([box_df,loc_df])
box_df.drop_duplicates(inplace=True)
box_df.columns=cols_df
box_df.sort_values(by='UTC',inplace=True)    
box_df.to_csv(box_file,mode='w',header=cols_df,index=False)
