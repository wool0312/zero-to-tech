import Link from "next/link";
import AnimatedCardGrid from "./AnimatedCardGrid.jsx";
import Nav from "./Nav.jsx";
import PageHeading from "./PageHeading.jsx";
import { profile } from "../data/profile.js";

export default function AboutView() {
  return (
    <AnimatedCardGrid className="dashboard-grid">
      <article className="hero-stage panel-full">
        <Nav />
        <PageHeading title={profile.about.title} subtitle={profile.about.subtitle} />
      </article>

      <article className="panel panel-full about-intro card">
        <p className="profile-eyebrow">{profile.eyebrow}</p>
        <h1>{profile.headline}</h1>
        <div className="about-intro-copy">
          {profile.bio.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        </div>
      </article>

      {profile.about.sections.map((section, index) => (
        <article className="panel panel-half about-detail card" key={section.id}>
          <span className="about-index" aria-hidden="true">0{index + 1}</span>
          <p className="section-kicker">{section.kicker}</p>
          <h2>{section.title}</h2>
          <p>{section.copy}</p>
        </article>
      ))}

      <Link className="panel panel-full about-back card" href="/">
        <span aria-hidden="true">←</span>
        返回个人主页
      </Link>
    </AnimatedCardGrid>
  );
}
