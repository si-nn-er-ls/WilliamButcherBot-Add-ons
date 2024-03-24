<h1 align="center"> 
    ✨ WilliamButcherBot Add-ons✨ 
</h1>

This repo consists of few Add-ons for [@WilliamButcherBot](https://github.com/TheHamkerCat/WilliamButcherBot)

## Available Add-ons

1. **Afk**
2. **Filemanager**
3. **Emoji Captcha** 

## patch installation

```console
si-nn-er-ls@kali:~$ git clone https://github.com/thehamkercat/WilliamButcherBot
si-nn-er-ls@kali:~$ git clone https://github.com/si-nn-er-ls/WilliamButcherBot-Add-ons Add-ons && rm -rf Add-ons/.git
si-nn-er-ls@kali:~$ sudo apt install wget rsync -y
si-nn-er-ls@kali:~$ rsync -av Add-ons/ WilliamButcherBot/ && rm -rf Add-ons
si-nn-er-ls@kali:~$ cd WilliamButcherBot
si-nn-er-ls@kali:~$ wget https://github.com/samuelngs/apple-emoji-linux/releases/download/v16.4-patch.1/AppleColorEmoji.ttf
si-nn-er-ls@kali:~$ pip3 install -U -r requirements.txt
si-nn-er-ls@kali:~$ cp sample_config.py config.py
```