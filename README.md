# Pioneer X-SMC55S custom component for Home Assistant

install:  
```sh
cd ~/.homeassistant/custom_components
git clone https://github.com/loop333/ha_pioneer_media_player pioneer
```
configuration.yaml:  
```yaml
media_player:
  - platform: pioneer
    name: pioneer
    host: <ip_address>
    port: 8102
    timeout: 1
```
