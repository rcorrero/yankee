### Miniconda setup ###
MINICONDA=https://repo.anaconda.com/miniconda/Miniconda3-py39_4.12.0-Linux-x86_64.sh
MINIOUTPATH=miniconda.sh
CONDAENV=yankee
SETUPFILE=$CONDAENV.txt

# wget -O $MINIOUTPATH $MINICONDA
bash $MINIOUTPATH
conda create --name $CONDAENV --file $SETUPFILE

### Git setup ###
# Uncomment the following lines if installing without pulling from git first
#sudo apt-get update
#sudo apt-get install git-all -y
#GITPATH=https://github.com/rcorrero/$CONDAENV.git
#git clone $GITPATH
#echo "__pycache__ \n$MINIOUTPATH \nparameters/ \ndata/ \nmodels/ \nlogs/" >> .gitignore

# ### Directory setup ###
# mkdir parameters
# mkdir parameters/experiments
# mkdir data
# mkdir models
# mkdir logs

### Setup Python script ###
# conda run -n $CONDAENV python -m setup

conda run -n $CONDAENV pip3 install light-pipe \
    && pip3 install aiohttp \
    && pip3 install Pillow \
    && pip3 install google-cloud-storage

### GCloud Setup
# gcloud init --no-browser      