from textwrap import dedent

BIND_PROMPT = dedent("""
        你尚未绑定 SteamID，请使用以下两种方式之一完成绑定：
    
        【方式一：通过网站绑定】
        1. 访问：https://forum.axekz.com/
        2. 使用 **QQ号码邮箱** 注册并验证账号
        3. 在个人主页设置中绑定你的 SteamID
        4. 回到 QQ 使用任意指令（如 /info /绑定 /wl /qd 等）即可完成绑定
    
        【方式二：游戏内生成绑定码】
        1. 在游戏中输入指令：!bindqq
        2. 将返回的绑定码私聊发送给机器人：/bind ABCDEFG
    """)
