import Link from "next/link";

export default function ProfileCard({ profile }) {
  const { avatar, eyebrow, headline, bio = [], tags = [], aboutLink } = profile;

  return (
    <article className="panel panel-full profile-card card">
      <div className="profile-portrait" aria-label={avatar.alt}>
        <div className="profile-orbit profile-orbit-one" aria-hidden="true" />
        <div className="profile-orbit profile-orbit-two" aria-hidden="true" />
        <div className="profile-avatar">
          {avatar.src ? (
            <img src={avatar.src} alt={avatar.alt} />
          ) : (
            <span aria-hidden="true">{avatar.initials}</span>
          )}
        </div>
      </div>

      <div className="profile-content">
        {eyebrow ? <p className="profile-eyebrow">{eyebrow}</p> : null}
        <h2 className="profile-headline">{headline}</h2>

        <div className="profile-bio">
          {bio.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>

        {tags.length ? (
          <ul className="profile-tags" aria-label="关注方向">
            {tags.map((tag) => (
              <li key={tag.id} className={`profile-tag profile-tag-${tag.tone}`}>
                <span className="profile-tag-dot" aria-hidden="true" />
                {tag.label}
              </li>
            ))}
          </ul>
        ) : null}

        {aboutLink?.href && aboutLink?.label ? (
          <Link className="profile-link" href={aboutLink.href}>
            <span>{aboutLink.label}</span>
            <span className="profile-link-arrow" aria-hidden="true">↗</span>
          </Link>
        ) : null}
      </div>
    </article>
  );
}
