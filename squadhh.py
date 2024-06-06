import re
import requests
import time
import configparser
import random
from datetime import datetime, timedelta

# 从 hh.ini 配置文件中读取配置
config = configparser.ConfigParser()
config.read('hh.ini')
API_KEY = config.get('settings', 'steam_api_key')
BAN_URL = config.get('settings', 'ban_url')
CLOUD_WHITELIST_URL = config.get('settings', 'cloud_whitelist_url')

# 从 rconlog.txt 中提取 steam64id
def extract_steam64id(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        content = file.read()
    steam64id_list = re.findall(r'steam: (\d{17})', content)
    return steam64id_list

# 从 white.txt 中提取白名单 steam64id
def load_whitelist(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        whitelist = file.read().splitlines()
    return whitelist

# 从云端获取白名单
def fetch_cloud_whitelist(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        whitelist = response.text.splitlines()
        return whitelist
    except requests.RequestException as e:
        print(f'获取云端白名单失败: {e}')
        return []

# 获取玩家信息，重试3次
def get_player_info(steam64id):
    games_url = f'http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={API_KEY}&steamid={steam64id}&format=json'
    player_url = f'http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={API_KEY}&steamids={steam64id}'
    friends_url = f'http://api.steampowered.com/ISteamUser/GetFriendList/v0001/?key={API_KEY}&steamid={steam64id}&relationship=friend'
    badges_url = f'http://api.steampowered.com/IPlayerService/GetBadges/v1/?key={API_KEY}&steamid={steam64id}'

    attempts = 3

    for attempt in range(attempts):
        game_hours = None
        game_count = None
        steam_level = None
        player_name = None
        friend_count = None
        badge_count = None

        try:
            games_response = requests.get(games_url, timeout=10).json()
            if 'response' in games_response and 'games' in games_response['response']:
                for game in games_response['response']['games']:
                    if game['appid'] == 393380:
                        game_hours = game['playtime_forever'] / 60
                game_count = len(games_response['response']['games'])
            else:
                print(f'无法查询到游戏信息: {steam64id}')
        except Exception as e:
            print(f'查询游戏信息出错: {steam64id}, 错误: {e}')

        try:
            player_response = requests.get(player_url, timeout=10).json()
            if 'response' in player_response and 'players' in player_response['response'] and player_response['response']['players']:
                player = player_response['response']['players'][0]
                player_name = player.get('personaname', '未知用户')
                if 'communityvisibilitystate' in player:
                    steam_level = player['communityvisibilitystate']
                else:
                    print(f'无法查询到Steam等级: {steam64id}')
            else:
                print(f'无法查询到玩家信息: {steam64id}')
        except Exception as e:
            print(f'查询玩家信息出错: {steam64id}, 错误: {e}')

        try:
            friends_response = requests.get(friends_url, timeout=10).json()
            if 'friendslist' in friends_response and 'friends' in friends_response['friendslist']:
                friend_count = len(friends_response['friendslist']['friends'])
            else:
                print(f'无法查询到好友信息: {steam64id}')
        except Exception as e:
            print(f'查询好友信息出错: {steam64id}, 错误: {e}')

        try:
            badges_response = requests.get(badges_url, timeout=10).json()
            if 'response' in badges_response and 'badges' in badges_response['response']:
                badge_count = len(badges_response['response']['badges'])
            else:
                print(f'无法查询到勋章信息: {steam64id}')
        except Exception as e:
            print(f'查询勋章信息出错: {steam64id}, 错误: {e}')

        if game_hours is not None and steam_level is not None and game_count is not None and friend_count is not None and badge_count is not None:
            return game_hours, steam_level, game_count, player_name, friend_count, badge_count

        print(f'重试获取玩家信息: {steam64id}, 第 {attempt + 1} 次尝试失败')
        time.sleep(2)  # 重试之前等待2秒

    return game_hours, steam_level, game_count, player_name, friend_count, badge_count

# 计算得分
def calculate_score(game_hours, steam_level, game_count, player_name, friend_count, badge_count):
    score = 0
    if game_hours is not None:
        if game_hours >= 300:
            score += 85
        elif game_hours < 100:
            score -= 45
    else:
        score -= 25
        print('无法查询到游戏时长.')

    if steam_level is not None:
        if steam_level >= 10:
            score += 50
        elif steam_level >= 5:
            score += 35
        elif steam_level >= 3:
            score += 20
        else:
            score -= 20
    else:
        score -= 5
        print('无法查询到Steam等级.')

    if game_count is not None:
        if game_count < 5:
            score -= 10
        elif 5 <= game_count <= 10:
            score += 10
        elif game_count > 10:
            score += 25
    else:
        score -= 5
        print('无法查询到游戏数量.')

    if player_name is not None and player_name.isdigit():
        score -= 15
        print(f'玩家昵称为纯数字: {player_name}, 扣除15分')

    if player_name is not None and re.search(r'[\u4e00-\u9fff]', player_name):
        score += 10
        print(f'玩家昵称包含中文字符: {player_name}, 加10分')

    if player_name is not None and '76561199' in player_name:
        score -= 10
        print(f'玩家昵称包含 "76561199": {player_name}, 扣10分')

    if friend_count is not None:
        score += friend_count * 5
        print(f'玩家有 {friend_count} 个好友, 加分 {friend_count * 5} 分')

    if badge_count is not None:
        score += badge_count * 5
        print(f'玩家有 {badge_count} 个勋章, 加分 {badge_count * 5} 分')

    return score

# 记录到疑似黑号文件
def log_suspected_black_account(steam64id, player_name):
    with open('疑似黑号.txt', 'a', encoding='utf-8') as file:
        file.write(f'{player_name}, {steam64id}\n')

# 生成8位随机数
def generate_random_id():
    return ''.join(random.choices('0123456789', k=8))

# 发送封禁请求，重试3次
def send_ban_request(steam64id):
    random_id = generate_random_id()
    reason = f'本封禁为黑号自动封禁插件封禁可进群解封-此封禁id需截图- (封禁ID: {random_id})'
    params = {
        'id': steam64id,
        'reason': reason,
        'time': '7d'
    }
    attempts = 3
    for attempt in range(attempts):
        try:
            print(f'发送封禁请求: {params}')  # 打印请求数据
            response = requests.get(BAN_URL, params=params, timeout=10)  # 使用GET请求
            print(f'封禁请求响应状态码: {response.status_code}')  # 打印响应状态码
            print(f'封禁请求响应内容: {response.text}')  # 打印响应内容
            if response.status_code == 200:
                response_json = response.json()
                if 'message' in response_json and response_json['message'] == '已将该玩家封禁':
                    return True
        except requests.exceptions.RequestException as e:
            print(f'连接到 {BAN_URL} 出错: {e}')
        time.sleep(2)  # 重试之前等待2秒
    return False

def main():
    whitelist = load_whitelist('white.txt')
    cloud_whitelist = fetch_cloud_whitelist(CLOUD_WHITELIST_URL)
    ban_count = 0
    ban_limit = 12
    start_time = datetime.now()
    time_window = timedelta(minutes=25)

    while True:
        steam64id_list = extract_steam64id('rconlog.txt')
        for steam64id in steam64id_list:
            if steam64id in whitelist:
                print(f'{steam64id} 在本地白名单中，跳过封禁')
                continue

            if steam64id in cloud_whitelist:
                print(f'{steam64id} 在云端白名单中，跳过封禁')
                continue

            game_hours, steam_level, game_count, player_name, friend_count, badge_count = get_player_info(steam64id)
            if game_hours is None and steam_level is None and game_count is None:
                log_suspected_black_account(steam64id, player_name or '未知用户')
                print(f'记录到疑似黑号: {steam64id} (昵称: {player_name})')
                continue

            score = calculate_score(game_hours, steam_level, game_count, player_name, friend_count, badge_count)
            if score < 50:
                current_time = datetime.now()
                if current_time - start_time > time_window:
                    ban_count = 0
                    start_time = current_time
                    print("25分钟窗口重置")

                if ban_count < ban_limit:
                    if send_ban_request(steam64id):
                        print(f'成功封禁 {steam64id}')
                        ban_count += 1
                        cloud_whitelist = fetch_cloud_whitelist(CLOUD_WHITELIST_URL)  # 成功封禁后更新云端白名单
                    else:
                        print(f'封禁失败 {steam64id}')
                else:
                    print("25分钟内封禁数量达到上限，跳过封禁")
            else:
                print(f'{steam64id} 不是黑号. 账户得分: {score}')
        time.sleep(120)  # 每120秒执行一次

if __name__ == '__main__':
    main()





