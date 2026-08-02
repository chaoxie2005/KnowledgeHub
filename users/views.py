import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.utils.text import gettext_lazy as _
from .models import UserProfile
from django.contrib.auth.models import User

# 中国省份-城市映射数据
PROVINCE_CITY_MAP = {
    "北京市": ["东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区", "顺义区", "通州区", "大兴区", "房山区", "昌平区", "怀柔区", "平谷区", "密云区", "延庆区"],
    "天津市": ["和平区", "河东区", "河西区", "南开区", "河北区", "红桥区", "东丽区", "西青区", "津南区", "北辰区", "武清区", "宝坻区", "滨海新区", "宁河区", "静海区", "蓟州区"],
    "上海市": ["黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区", "闵行区", "宝山区", "嘉定区", "浦东新区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"],
    "重庆市": ["渝中区", "江北区", "南岸区", "沙坪坝区", "九龙坡区", "大渡口区", "北碚区", "渝北区", "巴南区", "万州区", "涪陵区", "黔江区", "长寿区", "江津区", "合川区", "永川区"],
    "河北省": ["石家庄市", "唐山市", "秦皇岛市", "邯郸市", "邢台市", "保定市", "张家口市", "承德市", "沧州市", "廊坊市", "衡水市"],
    "山西省": ["太原市", "大同市", "阳泉市", "长治市", "晋城市", "朔州市", "晋中市", "运城市", "忻州市", "临汾市", "吕梁市"],
    "内蒙古自治区": ["呼和浩特市", "包头市", "乌海市", "赤峰市", "通辽市", "鄂尔多斯市", "呼伦贝尔市", "巴彦淖尔市", "乌兰察布市", "兴安盟", "锡林郭勒盟", "阿拉善盟"],
    "辽宁省": ["沈阳市", "大连市", "鞍山市", "抚顺市", "本溪市", "丹东市", "锦州市", "营口市", "阜新市", "辽阳市", "盘锦市", "铁岭市", "朝阳市", "葫芦岛市"],
    "吉林省": ["长春市", "吉林市", "四平市", "辽源市", "通化市", "白山市", "松原市", "白城市", "延边朝鲜族自治州"],
    "黑龙江省": ["哈尔滨市", "齐齐哈尔市", "鸡西市", "鹤岗市", "双鸭山市", "大庆市", "伊春市", "佳木斯市", "七台河市", "牡丹江市", "黑河市", "绥化市", "大兴安岭地区"],
    "江苏省": ["南京市", "无锡市", "徐州市", "常州市", "苏州市", "南通市", "连云港市", "淮安市", "盐城市", "扬州市", "镇江市", "泰州市", "宿迁市"],
    "浙江省": ["杭州市", "宁波市", "温州市", "嘉兴市", "湖州市", "绍兴市", "金华市", "衢州市", "舟山市", "台州市", "丽水市"],
    "安徽省": ["合肥市", "芜湖市", "蚌埠市", "淮南市", "马鞍山市", "淮北市", "铜陵市", "安庆市", "黄山市", "滁州市", "阜阳市", "宿州市", "六安市", "亳州市", "池州市", "宣城市"],
    "福建省": ["福州市", "厦门市", "莆田市", "三明市", "泉州市", "漳州市", "南平市", "龙岩市", "宁德市"],
    "江西省": ["南昌市", "景德镇市", "萍乡市", "九江市", "新余市", "鹰潭市", "赣州市", "吉安市", "宜春市", "抚州市", "上饶市"],
    "山东省": ["济南市", "青岛市", "淄博市", "枣庄市", "东营市", "烟台市", "潍坊市", "济宁市", "泰安市", "威海市", "日照市", "临沂市", "德州市", "聊城市", "滨州市", "菏泽市"],
    "河南省": ["郑州市", "开封市", "洛阳市", "平顶山市", "安阳市", "鹤壁市", "新乡市", "焦作市", "濮阳市", "许昌市", "漯河市", "三门峡市", "南阳市", "商丘市", "信阳市", "周口市", "驻马店市", "济源市"],
    "湖北省": ["武汉市", "黄石市", "十堰市", "宜昌市", "襄阳市", "鄂州市", "荆门市", "孝感市", "荆州市", "黄冈市", "咸宁市", "随州市", "恩施土家族苗族自治州", "仙桃市", "潜江市", "天门市"],
    "湖南省": ["长沙市", "株洲市", "湘潭市", "衡阳市", "邵阳市", "岳阳市", "常德市", "张家界市", "益阳市", "郴州市", "永州市", "怀化市", "娄底市", "湘西土家族苗族自治州"],
    "广东省": ["广州市", "韶关市", "深圳市", "珠海市", "汕头市", "佛山市", "江门市", "湛江市", "茂名市", "肇庆市", "惠州市", "梅州市", "汕尾市", "河源市", "阳江市", "清远市", "东莞市", "中山市", "潮州市", "揭阳市", "云浮市"],
    "广西壮族自治区": ["南宁市", "柳州市", "桂林市", "梧州市", "北海市", "防城港市", "钦州市", "贵港市", "玉林市", "百色市", "贺州市", "河池市", "来宾市", "崇左市"],
    "海南省": ["海口市", "三亚市", "三沙市", "儋州市", "五指山市", "琼海市", "文昌市", "万宁市", "东方市"],
    "四川省": ["成都市", "自贡市", "攀枝花市", "泸州市", "德阳市", "绵阳市", "广元市", "遂宁市", "内江市", "乐山市", "南充市", "眉山市", "宜宾市", "广安市", "达州市", "雅安市", "巴中市", "资阳市", "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州"],
    "贵州省": ["贵阳市", "六盘水市", "遵义市", "安顺市", "毕节市", "铜仁市", "黔西南布依族苗族自治州", "黔东南苗族侗族自治州", "黔南布依族苗族自治州"],
    "云南省": ["昆明市", "曲靖市", "玉溪市", "保山市", "昭通市", "丽江市", "普洱市", "临沧市", "楚雄彝族自治州", "红河哈尼族彝族自治州", "文山壮族苗族自治州", "西双版纳傣族自治州", "大理白族自治州", "德宏傣族景颇族自治州", "怒江傈僳族自治州", "迪庆藏族自治州"],
    "西藏自治区": ["拉萨市", "日喀则市", "昌都市", "林芝市", "山南市", "那曲市", "阿里地区"],
    "陕西省": ["西安市", "铜川市", "宝鸡市", "咸阳市", "渭南市", "延安市", "汉中市", "榆林市", "安康市", "商洛市"],
    "甘肃省": ["兰州市", "嘉峪关市", "金昌市", "白银市", "天水市", "武威市", "张掖市", "平凉市", "酒泉市", "庆阳市", "定西市", "陇南市", "临夏回族自治州", "甘南藏族自治州"],
    "青海省": ["西宁市", "海东市", "海北藏族自治州", "黄南藏族自治州", "海南藏族自治州", "果洛藏族自治州", "玉树藏族自治州", "海西蒙古族藏族自治州"],
    "宁夏回族自治区": ["银川市", "石嘴山市", "吴忠市", "固原市", "中卫市"],
    "新疆维吾尔自治区": ["乌鲁木齐市", "克拉玛依市", "吐鲁番市", "哈密市", "昌吉回族自治州", "博尔塔拉蒙古自治州", "巴音郭楞蒙古自治州", "阿克苏地区", "克孜勒苏柯尔克孜自治州", "喀什地区", "和田地区", "伊犁哈萨克自治州", "塔城地区", "阿勒泰地区", "石河子市"],
    "台湾省": ["台北市", "高雄市", "台中市", "台南市", "基隆市", "新竹市", "嘉义市", "桃园市", "新北市"],
    "香港特别行政区": ["中西区", "湾仔区", "东区", "南区", "油尖旺区", "深水埗区", "九龙城区", "黄大仙区", "观塘区", "荃湾区", "屯门区", "元朗区", "北区", "大埔区", "沙田区", "西贡区", "离岛区"],
    "澳门特别行政区": ["澳门半岛", "氹仔", "路环", "路氹城"],
}


@login_required(login_url='authentication:login')
def user_center(request):
    """用户个人中心"""
    # 直接使用 request.user，它就是当前登录的 User 对象
    user = request.user
    # 使用 get_or_create 可以更简洁地处理 UserProfile 的创建
    user_profile, created = UserProfile.objects.get_or_create(user=user)

    context = {"user": user, "user_profile": user_profile}
    return render(request, "users/user_center.html", context)


# 登录保护：未登录用户无法访问
@login_required(login_url="authentication:login")
def edit_user(request):
    """编辑用户信息"""
    # 确保当前用户有对应的UserProfile（无则创建）
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == "GET":
        # GET请求：传递用户现有数据到模板
        context = {
            "profile": profile,
            "gender_choices": UserProfile.USER_GENDER_TYPE,  # 性别选项
            "province_city_map_json": json.dumps(PROVINCE_CITY_MAP, ensure_ascii=False),
        }
        return render(request, "users/edit_user.html", context)

    elif request.method == "POST":
        try:
            # ========== 1. 提取并校验表单数据 ==========
            # 基础信息
            nickname = request.POST.get("nickname", "").strip()
            gender = request.POST.get("gender", "unknown")
            phone = request.POST.get("phone", "").strip()
            email = request.POST.get("email", "").strip()
            bio = request.POST.get("bio", "").strip()

            # 地址信息
            address = request.POST.get("address", "").strip()
            city = request.POST.get("city", "").strip()
            state = request.POST.get("state", "").strip()

            # 头像文件（注意是FILES不是File）
            avatar_file = request.FILES.get("avatar")

            # ========== 2. 数据校验（和模型validators逻辑一致） ==========
            # 昵称校验
            if nickname:
                import re

                if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9_]+$", nickname):
                    raise ValidationError(_("昵称只能包含中文、字母、数字和下划线"))
                if len(nickname) > 50:
                    raise ValidationError(_("昵称不能超过50个字符"))

            # 性别校验
            if gender not in [choice[0] for choice in UserProfile.USER_GENDER_TYPE]:
                raise ValidationError(_("性别选择无效"))

            # 手机号校验
            if phone:
                if not re.match(r"^1[3-9]\d{9}$", phone):
                    raise ValidationError(_("请输入有效的11位手机号"))

            # 邮箱校验
            if email:
                from django.core.validators import validate_email

                validate_email(email)  # Django内置邮箱校验

            # 个人简介校验
            if bio:
                if not re.match(r"^[^<>{}$]*$", bio):
                    raise ValidationError(_("个人简介不能包含特殊字符"))
                if len(bio) > 500:
                    raise ValidationError(_("个人简介不能超过500个字符"))

            # 头像文件校验
            if avatar_file:
                # 校验文件类型
                allowed_extensions = ["jpg", "jpeg", "png", "webp"]
                file_ext = avatar_file.name.split(".")[-1].lower()
                if file_ext not in allowed_extensions:
                    raise ValidationError(_("头像仅支持jpg/jpeg/png/webp格式"))

                # 校验文件大小（2MB）
                max_size = 4 * 1024 * 1024
                if avatar_file.size > max_size:
                    raise ValidationError(_("头像大小不能超过4MB"))

            # ========== 3. 赋值并保存数据 ==========
            # 基础信息赋值
            if nickname:
                profile.nickname = nickname
            profile.gender = gender
            if phone:
                profile.phone = phone
            if email:
                profile.email = email
                # 可选：同步更新User模型的邮箱
                request.user.email = email
                request.user.save()
            if bio:
                profile.bio = bio

            # 地址信息赋值
            if address:
                profile.address = address
            if city:
                profile.city = city
            if state:
                profile.state = state

            # 头像赋值（有上传文件才更新）
            if avatar_file:
                profile.avatar = avatar_file

            # 保存Profile（触发模型的auto_now更新时间）
            profile.save()

            # ========== 4. 提示并跳转 ==========
            messages.success(request, "信息修改成功！")
            return redirect("users:user_center")  # 成功时直接返回跳转

        # ========== 异常处理 ==========
        except ValidationError as e:
            # 数据校验失败
            messages.error(request, f"修改失败：{e.message}")
        except Exception as e:
            # 其他未知错误（如数据库错误）
            messages.error(request, f"系统错误：{str(e)}")

        context = {
            "profile": profile,
            "gender_choices": UserProfile.USER_GENDER_TYPE,
            "post_data": request.POST,  # 保留用户已填数据，提升体验
            "province_city_map_json": json.dumps(PROVINCE_CITY_MAP, ensure_ascii=False),
        }
        return render(request, "users/edit_user.html", context)  # 失败时返回编辑页


@login_required(login_url="authentication:login")
def user_center(request, user_id=None):
    """用户个人中心：支持查看自己或他人"""
    if user_id:
        # 查看他人个人中心
        user = get_object_or_404(User, id=user_id)
    else:
        # 查看自己的个人中心
        user = request.user

    user_profile, created = UserProfile.objects.get_or_create(user=user)
    context = {"user": user, "user_profile": user_profile}
    return render(request, "users/user_center.html", context)


def user_detail(request, user_id):
    """用户个人中心"""
    user = get_object_or_404(User, id=user_id)
    user_profile, created = UserProfile.objects.get_or_create(user=user)

    context = {"user": user, "user_profile": user_profile}
    return render(request, 'users/user_detail.html', context)
