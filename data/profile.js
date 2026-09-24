// 首页个人卡片的唯一内容来源。
// 头像、简介、标签和详情入口都在这里修改；可选字段为空时会自动隐藏。
export const profile = {
  avatar: {
    src: "",
    alt: "Wool 的个人头像",
    initials: "W",
  },
  eyebrow: "Hi, This is WOOL",
  headline: "正在成长的全栈开发者",
  bio: [
    "有选择的地方就有艺术",
  ],
  tags: [
    { id: "fullstack", label: "全栈探索", tone: "blue" },
    { id: "learning", label: "终身学习", tone: "purple" },
    { id: "Arsenal-FC", label: "COYG", tone: "red" },
  ],
  aboutLink: {
    label: "更多关于我",
    href: "/about",
  },
  about: {
    title: "关于我",
    subtitle: "一份随着学习与实践持续生长的个人说明",
    sections: [
      {
        id: "building",
        kicker: "正在构建",
        title: "AI Agent",
        copy: "我正在学习如何把Agent开发与真实需求连接起来, 希望让这个世界变得更有趣一点。",
      },
      {
        id: "curiosity",
        kicker: "保持好奇",
        title: "不只关心技术本身",
        copy: "阅读、写作和观察生活，帮助我理解人如何使用技术，也让我持续发现值得解决的问题。",
      },
    ],
  },
};
