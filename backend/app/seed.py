"""Seed question bank + demo team names.

Every question has:
  text/options in en + vi, `correct` (index 0-3, or None for polls),
  `setup` (what the quiz says to set up the joke), `punchline` (comedian's
  suggested tag, shown to the HOST ONLY after reveal) and `notes` (host only).

Lines marked VI-CHECK should be reviewed by a native Vietnamese speaker.
"""

def q(text_en, text_vi, options, correct, setup, punchline, notes, time_limit=20, kind="quiz"):
    return {
        "type": kind,
        "text": {"en": text_en, "vi": text_vi},
        "options": [{"en": en, "vi": vi} for en, vi in options],
        "correct": correct,
        "time_limit": time_limit,
        "setup": setup,
        "punchline": punchline,
        "notes": notes,
    }


def writein(text_en, text_vi, setup, punchline, notes, demo_answers, time_limit=40):
    out = q(text_en, text_vi, [], None, setup, punchline, notes, time_limit=time_limit, kind="writein")
    out["demo_answers"] = demo_answers
    return out


SEED_QUESTIONS = [
    q("How many hearts does an octopus have?",
      "Con bạch tuộc có bao nhiêu trái tim?",
      [("1", "1"), ("2", "2"), ("3", "3"), ("8, one per arm", "8, mỗi xúc tu một cái")],
      2,
      {"en": "Three hearts. And it still can't find someone to love in District 1.",
       "vi": "Ba trái tim mà vẫn ế ở Quận 1."},  # VI-CHECK
      {"en": "Whoever picked 8: you're the reason dating apps exist.",
       "vi": "Đội nào chọn 8: các bạn là lý do app hẹn hò tồn tại."},  # VI-CHECK
      "Two hearts pump blood to the gills, one to the body. Blood is blue (copper-based)."),

    q("Before 1976, what was Ho Chi Minh City's official name?",
      "Trước năm 1976, tên chính thức của TP. Hồ Chí Minh là gì?",
      [("Saigon", "Sài Gòn"), ("Hanoi South", "Nam Hà Nội"), ("Chợ Lớn", "Chợ Lớn"), ("Gia Định City", "Thành phố Gia Định")],
      0,
      {"en": "Officially it changed in 1976. Unofficially, nobody got the memo.",
       "vi": "Chính thức đổi tên năm 1976. Không chính thức thì… chưa ai nhận được thông báo."},  # VI-CHECK
      {"en": "Anyone who picked 'Hanoi South': please don't say that north of Huế.",
       "vi": "Ai chọn 'Nam Hà Nội': đừng nói câu đó ở ngoài Huế nha."},  # VI-CHECK
      "Renamed 2 July 1976. 'Sài Gòn' is still used daily, e.g. Saigon River, Sài Gòn Beer."),

    q("Cà phê sữa đá = coffee plus what?",
      "Cà phê sữa đá = cà phê cộng với gì?",
      [("Fresh milk + sugar", "Sữa tươi + đường"), ("Condensed milk + ice", "Sữa đặc + đá"),
       ("Coconut cream + salt", "Kem dừa + muối"), ("Egg yolk + honey", "Lòng đỏ trứng + mật ong")],
      1,
      {"en": "Condensed milk and ice: the only relationship in Saigon that never melts down.",
       "vi": "Sữa đặc và đá: mối quan hệ duy nhất ở Sài Gòn không bao giờ tan."},  # VI-CHECK
      {"en": "Egg yolk team: that's Hanoi's egg coffee. Wrong city, right vibes.",
       "vi": "Đội lòng đỏ trứng: đó là cà phê trứng Hà Nội. Sai thành phố, đúng vibe."},
      "Condensed milk became standard because fresh milk was scarce and spoiled fast in the heat."),

    q("Which river runs right through the middle of Ho Chi Minh City?",
      "Con sông nào chảy qua trung tâm TP. Hồ Chí Minh?",
      [("Mekong River", "Sông Mê Kông"), ("Red River", "Sông Hồng"),
       ("Saigon River", "Sông Sài Gòn"), ("Perfume River", "Sông Hương")],
      2,
      {"en": "It's called the Saigon River. The city changed its name; the river said 'no thanks'.",
       "vi": "Sông Sài Gòn. Thành phố đổi tên, còn con sông thì 'thôi, khỏi'."},  # VI-CHECK
      {"en": "Mekong pickers: close, it's only a 3-hour bus and two bánh mì away.",
       "vi": "Ai chọn Mê Kông: gần đúng, chỉ cách 3 tiếng xe buýt và hai ổ bánh mì."},  # VI-CHECK
      "The Red River is in Hanoi; the Perfume River (Sông Hương) is in Huế."),

    q("POLL: Worst excuse for being late in Saigon?",
      "BÌNH CHỌN: Lý do đi trễ tệ nhất ở Sài Gòn?",
      [("It rained for 5 minutes", "Trời mưa có 5 phút"),
       ("Grab went to the wrong District 1", "Grab chạy nhầm Quận 1 khác"),
       ("Street flooded, I'm a boat now", "Đường ngập, giờ tôi là chiếc thuyền"),
       ("'On the way' (still in bed)", "'Đang tới' (vẫn nằm trên giường)")],
      None,
      {"en": "No wrong answers. Only answers your boss has heard before.",
       "vi": "Không có đáp án sai. Chỉ có đáp án sếp bạn đã nghe rồi."},
      {"en": "Whoever picked 'On the way': we know. Your mum knows. Your Grab driver knows.",
       "vi": "Ai chọn 'Đang tới': tụi tui biết. Mẹ bạn biết. Tài xế Grab cũng biết."},  # VI-CHECK
      "Poll: no correct answer, no points in Tier 1. Ask the biggest group to defend themselves.",
      time_limit=15, kind="poll"),

    q("The bread in bánh mì was introduced by which country?",
      "Bánh mì (ổ bánh) được du nhập từ nước nào?",
      [("France", "Pháp"), ("China", "Trung Quốc"), ("Portugal", "Bồ Đào Nha"), ("USA", "Mỹ")],
      0,
      {"en": "France brought the baguette. Vietnam made it actually worth eating.",
       "vi": "Pháp mang ổ bánh mì tới. Việt Nam làm cho nó đáng ăn."},
      {"en": "USA pickers think every good thing was invented at a drive-through.",
       "vi": "Đội chọn Mỹ tưởng cái gì ngon cũng được phát minh ở quầy drive-through."},  # VI-CHECK
      "Vietnamese baguettes usually use some rice flour, so they're lighter with a thin crust."),

    writein("WRITE-IN: You know you've lived in Saigon too long when…",
            "TỰ VIẾT: Bạn biết mình ở Sài Gòn quá lâu khi…",
            {"en": "The room writes the jokes now. I just read them out and take the credit.",
             "vi": "Giờ cả phòng viết joke. Tôi chỉ đọc và nhận công thôi."},  # VI-CHECK
            {"en": "If yours didn't make the screen, it was either too rude or too boring. You'll never know which.",
             "vi": "Nếu câu của bạn không lên màn hình: hoặc quá bậy, hoặc quá chán. Bạn sẽ không bao giờ biết."},  # VI-CHECK
            "Write-in: approve up to 6 (duplicates are grouped), then the room votes. +100 laugh per approved answer, +300 for the winner.",
            ["You honk at people on the sidewalk", "you honk at people on the sidewalk!", "You think 28°C is jacket weather",
             "You own 3 raincoats and are still wet", "Your Grab driver knows your mum", "you think 28°C is jacket weather",
             "You order cà phê sữa đá in your sleep", "You cross the road without looking. On purpose."]),
    q("What is Tết?",
      "Tết là gì?",
      [("Mid-Autumn Festival", "Tết Trung Thu"), ("Lunar New Year", "Tết Nguyên Đán"),
       ("National Day", "Quốc Khánh"), ("A type of noodle", "Một loại bún")],
      1,
      {"en": "Lunar New Year: the one week a year Saigon traffic is calm and your aunties are not.",
       "vi": "Tết: tuần duy nhất trong năm đường Sài Gòn vắng còn các cô dì thì không yên."},  # VI-CHECK
      {"en": "'A type of noodle' team, I respect the commitment to the bit.",
       "vi": "Đội chọn 'một loại bún': tôn trọng sự cống hiến cho trò đùa."},  # VI-CHECK
      "Tết Nguyên Đán. Trung Thu (Mid-Autumn) is also called 'Tết' informally, so expect arguments."),

    q("Phở noodles are made from…?",
      "Bánh phở được làm từ…?",
      [("Wheat", "Bột mì"), ("Rice", "Gạo"), ("Mung beans", "Đậu xanh"), ("Egg", "Trứng")],
      1,
      {"en": "Rice noodles. Wheat pickers have been eating ramen and lying to us.",
       "vi": "Bánh phở làm từ gạo. Ai chọn bột mì là đang ăn mì ramen rồi nói dối tụi mình."},  # VI-CHECK
      {"en": "Egg team: that's mì. It's okay. Everyone has a first day.",
       "vi": "Đội trứng: đó là mì. Không sao. Ai cũng có ngày đầu tiên."},
      "Flat rice noodles = bánh phở. Phở originated in the north, around Nam Định / Hanoi."),

    q("Vietnam is the world's #2 exporter of which drink crop?",
      "Việt Nam là nước xuất khẩu lớn thứ 2 thế giới về loại cây nào?",
      [("Tea", "Trà"), ("Cocoa", "Ca cao"), ("Coffee", "Cà phê"), ("Hops", "Hoa bia")],
      2,
      {"en": "Coffee. Which explains how anyone survives Saigon traffic at 8 a.m.",
       "vi": "Cà phê. Giải thích vì sao người ta sống sót qua giờ kẹt xe 8 giờ sáng."},
      {"en": "Hops team: you're not wrong about what tonight runs on.",
       "vi": "Đội hoa bia: các bạn không sai về thứ đang 'chạy' cái đêm nay."},  # VI-CHECK
      "Mostly robusta, grown in the Central Highlands (Tây Nguyên). Brazil is #1."),

    q("Bến Thành is a famous Saigon…?",
      "Bến Thành là một… nổi tiếng của Sài Gòn?",
      [("Bridge", "Cây cầu"), ("Market", "Khu chợ"), ("Pagoda", "Ngôi chùa"), ("Football club", "Câu lạc bộ bóng đá")],
      1,
      {"en": "A market, where the prices change depending on how foreign your accent is.",
       "vi": "Một khu chợ, nơi giá cả thay đổi theo giọng nói của bạn."},  # VI-CHECK
      {"en": "Football club pickers: you've been bargaining at the wrong stadium.",
       "vi": "Đội chọn CLB bóng đá: các bạn đi trả giá nhầm sân vận động rồi."},  # VI-CHECK
      "The current building dates from 1914. Its clock tower is a city symbol."),

    q("Vietnam's map is shaped like which letter?",
      "Bản đồ Việt Nam có hình chữ cái nào?",
      [("S", "S"), ("C", "C"), ("L", "L"), ("Z", "Z")],
      0,
      {"en": "An S. Like the route your Grab driver takes when you're in a hurry.",
       "vi": "Chữ S. Giống đường tài xế Grab chạy khi bạn đang vội."},
      {"en": "Z pickers: that's how you walk home after this bar.",
       "vi": "Đội chọn Z: đó là cách các bạn đi bộ về nhà sau quán này."},
      "Easy points. Use it to rebuild confidence after a hard one."),

    writein("WRITE-IN: Invent a terrible new bánh mì filling",
            "TỰ VIẾT: Sáng tạo một loại nhân bánh mì thật tệ",
            {"en": "Somewhere a bánh mì lady is reading these and crying.",
             "vi": "Đâu đó có một cô bán bánh mì đang đọc mấy câu này và khóc."},
            {"en": "Whoever wrote the winner: you're banned from every bakery in District 3.",
             "vi": "Đội viết câu thắng: bạn bị cấm cửa mọi tiệm bánh ở Quận 3."},  # VI-CHECK
            "Write-in. Read the grossest approved one slowly, like a wine review.",
            ["Durian and mayo", "durian & mayo", "Pineapple pizza bánh mì", "Just ice", "just ice.",
             "Leftover phở noodles", "Chocolate pâté", "Sầu riêng + pate"]),
    q("POLL: If tonight's host weren't a comedian, what job would they have?",
      "BÌNH CHỌN: Nếu MC tối nay không làm hài, họ sẽ làm nghề gì?",
      [("Grab driver", "Tài xế Grab"), ("Karaoke judge", "Giám khảo karaoke"),
       ("Bánh mì influencer", "Influencer bánh mì"), ("Tour guide who makes stuff up", "Hướng dẫn viên bịa chuyện")],
      None,
      {"en": "The room has spoken. The room is cruel.",
       "vi": "Cả phòng đã lên tiếng. Cả phòng thật tàn nhẫn."},
      {"en": "Honestly? 'Tour guide who makes stuff up' is basically this job already.",
       "vi": "Nói thật, 'hướng dẫn viên bịa chuyện' thì cũng là nghề này rồi."},
      "Self-roast moment. Pick the winning answer and run with it for 20 seconds.",
      time_limit=15, kind="poll"),

    q("Which animal replaces the rabbit in the Vietnamese zodiac?",
      "Con vật nào thay thế con thỏ trong 12 con giáp Việt Nam?",
      [("Dog", "Chó"), ("Cat", "Mèo"), ("Fox", "Cáo"), ("Duck", "Vịt")],
      1,
      {"en": "The cat. Vietnam looked at the rabbit and said: we can do cuter and meaner.",
       "vi": "Con mèo. Việt Nam nhìn con thỏ rồi nói: tụi tui có con dễ thương mà láo hơn."},  # VI-CHECK
      {"en": "Dog pickers: the dog is already in the zodiac. It doesn't need two jobs.",
       "vi": "Đội chọn chó: chó có trong 12 con giáp rồi. Nó không cần làm hai việc."},
      "Year of the Cat (Mão/Mẹo). Nobody fully agrees why; 'Mão' sounds like 'mèo' is a popular theory."),

    q("What is Vietnam's currency called?",
      "Đơn vị tiền tệ của Việt Nam là gì?",
      [("Dong", "Đồng"), ("Baht", "Baht"), ("Riel", "Riel"), ("Kip", "Kíp")],
      0,
      {"en": "The đồng. The only currency where you're a millionaire and still can't afford parking in District 1.",
       "vi": "Đồng. Đơn vị tiền tệ duy nhất mà bạn là triệu phú vẫn không đủ tiền gửi xe Quận 1."},  # VI-CHECK
      {"en": "Baht pickers: you're thinking of the Bangkok trip you keep promising your friends.",
       "vi": "Đội chọn Baht: đang nghĩ tới chuyến đi Bangkok hứa hoài chưa đi."},  # VI-CHECK
      "Baht = Thailand, Riel = Cambodia, Kip = Laos."),
]


FINALE_QUESTION = q(
    "FINALE: What is the tallest building in Vietnam?",
    "CHUNG KẾT: Toà nhà cao nhất Việt Nam là toà nào?",
    [("Landmark 81", "Landmark 81"), ("Bitexco Financial Tower", "Tháp Tài chính Bitexco"),
     ("Keangnam Landmark 72", "Keangnam Landmark 72"), ("Lotte Center Hanoi", "Lotte Center Hà Nội")],
    0,
    {"en": "Landmark 81. You can see it from anywhere in Saigon, which is lucky, because you'll never find parking near it.",
     "vi": "Landmark 81. Đứng đâu ở Sài Gòn cũng thấy, may ghê, vì bạn sẽ không bao giờ tìm được chỗ gửi xe gần đó."},  # VI-CHECK
    {"en": "Whoever bet 100% and got it wrong: that's not a wager, that's a personality.",
     "vi": "Ai cược 100% mà sai: đó không phải là cược, đó là tính cách."},  # VI-CHECK
    "Landmark 81: 461 m, opened 2018, Bình Thạnh. Wagers resolve on reveal; bottom-3 teams win double.",
    time_limit=25,
)
FINALE_QUESTION["final"] = True


DEMO_TEAMS = [
    ("Phở Real", "🍜", "We once ate phở for breakfast, lunch and dinner", "spicy", True),
    ("Bánh Mì Up, Scotty", "🥖", "Our captain can name 11 bánh mì fillings", "mild", False),
    ("Bún Voyage", "🚢", "Half of us are leaving Saigon next month", "mild", True),
    ("Lẩu and Order", "🍲", "We argue about hot pot rules every week", "off", False),
    ("Sài Gòn With The Wind", "💨", "We all ride the same scooter (not at once)", "spicy", True),
    ("Cà Phê Sữa Slay", "☕", "We drink 4 coffees before 10 a.m.", "mild", False),
    ("Spring Roll Call", "🌯", "Our team is 3 teachers and a dentist", "off", True),
    ("Mắm's the Word", "🤫", "We have never once won a pub quiz", "spicy", False),
]
