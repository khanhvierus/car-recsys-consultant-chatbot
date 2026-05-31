// import { useMemo } from "react";
// import { Link } from "react-router-dom";
// import {
//   Facebook,
//   Twitter,
//   Instagram,
//   Youtube,
//   Mail,
//   Phone,
//   MapPin,
// } from "lucide-react";

// const Footer = () => {
//   const currentYear = new Date().getFullYear();

//   const bgImages = [
//     "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1920&h=900&fit=crop&q=80",
//     "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1920&h=900&fit=crop&q=80",
//     "https://images.unsplash.com/photo-1544636331-e26879cd4d9b?w=1920&h=900&fit=crop&q=80",
//   ] as const;

//   const bgImage = useMemo(
//     () => bgImages[Math.floor(Math.random() * bgImages.length)],
//     []
//   );

//   const footerLinks = {
//     company: [
//       { label: "About Us", href: "#" },
//       { label: "Careers", href: "#" },
//       { label: "Press", href: "#" },
//       { label: "Blog", href: "#" },
//     ],
//     support: [
//       { label: "Help Center", href: "#" },
//       { label: "Contact Us", href: "#" },
//       { label: "FAQs", href: "#" },
//       { label: "Safety", href: "#" },
//     ],
//     legal: [
//       { label: "Terms of Service", href: "#" },
//       { label: "Privacy Policy", href: "#" },
//       { label: "Cookie Policy", href: "#" },
//       { label: "Accessibility", href: "#" },
//     ],
//   };

//   const socialLinks = [
//     { icon: Facebook, href: "#", label: "Facebook" },
//     { icon: Twitter, href: "#", label: "Twitter" },
//     { icon: Instagram, href: "#", label: "Instagram" },
//     { icon: Youtube, href: "#", label: "Youtube" },
//   ];

//   return (
//     <footer className="relative border-t border-border overflow-hidden">
//       {/* Outer background image - subtle */}
//       <div className="pointer-events-none absolute inset-0">
//         <div className="absolute inset-0 bg-secondary/50" />
//       </div>

//       {/* Main footer content */}
//       <div className="relative container mx-auto px-4 py-16">
//         <div className="relative overflow-hidden rounded-3xl border border-border/40">
//           {/* Background image - less blur like hero */}
//           <div className="pointer-events-none absolute inset-0" aria-hidden="true">
//             <img
//               src={bgImage}
//               alt=""
//               loading="lazy"
//               className="h-full w-full object-cover opacity-40 scale-105"
//               style={{ objectPosition: "center 40%" }}
//             />
//             {/* Gradient overlays for text readability */}
//             <div className="absolute inset-0 bg-gradient-to-r from-background via-background/70 to-transparent" />
//             <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-background/50" />
//           </div>

//           <div className="relative p-8 md:p-10">
//             {/* Brand section */}
//             <div className="mb-12">
//               <Link to="/" className="inline-block mb-6">
//                 <span className="text-4xl font-extrabold text-foreground font-sans">
//                   Car<span className="text-accent">Market</span>
//                 </span>
//               </Link>
//               <p className="text-muted-foreground mb-6 max-w-sm leading-relaxed">
//                 Your trusted destination for luxury and exotic vehicles. We connect
//                 discerning buyers with premium automobiles from around the world.
//               </p>
//               <div className="space-y-3">
//                 <a
//                   href="mailto:hello@carmarket.com"
//                   className="flex items-center gap-3 text-sm text-muted-foreground hover:text-accent transition-colors"
//                 >
//                   <Mail className="h-4 w-4" />
//                   hello@carmarket.com
//                 </a>
//                 <a
//                   href="tel:+15550123456"
//                   className="flex items-center gap-3 text-sm text-muted-foreground hover:text-accent transition-colors"
//                 >
//                   <Phone className="h-4 w-4" />
//                   +1 (555) 012-3456
//                 </a>
//                 <p className="flex items-center gap-3 text-sm text-muted-foreground">
//                   <MapPin className="h-4 w-4" />
//                   Los Angeles, California
//                 </p>
//               </div>
//             </div>

//             {/* Links sections - all on same row */}
//             <div className="grid grid-cols-2 sm:grid-cols-3 gap-8">
//               <div>
//                 <h4 className="font-heading text-sm font-semibold text-foreground uppercase tracking-wider mb-4">
//                   Company
//                 </h4>
//                 <ul className="space-y-3">
//                   {footerLinks.company.map((link) => (
//                     <li key={link.label}>
//                       <a
//                         href={link.href}
//                         className="text-sm text-muted-foreground hover:text-accent transition-colors"
//                       >
//                         {link.label}
//                       </a>
//                     </li>
//                   ))}
//                 </ul>
//               </div>

//               <div>
//                 <h4 className="font-heading text-sm font-semibold text-foreground uppercase tracking-wider mb-4">
//                   Support
//                 </h4>
//                 <ul className="space-y-3">
//                   {footerLinks.support.map((link) => (
//                     <li key={link.label}>
//                       <a
//                         href={link.href}
//                         className="text-sm text-muted-foreground hover:text-accent transition-colors"
//                       >
//                         {link.label}
//                       </a>
//                     </li>
//                   ))}
//                 </ul>
//               </div>

//               <div>
//                 <h4 className="font-heading text-sm font-semibold text-foreground uppercase tracking-wider mb-4">
//                   Legal
//                 </h4>
//                 <ul className="space-y-3">
//                   {footerLinks.legal.map((link) => (
//                     <li key={link.label}>
//                       <a
//                         href={link.href}
//                         className="text-sm text-muted-foreground hover:text-accent transition-colors"
//                       >
//                         {link.label}
//                       </a>
//                     </li>
//                   ))}
//                 </ul>
//               </div>
//             </div>
//           </div>
//         </div>
//       </div>

//       {/* Bottom bar */}
//       <div className="relative border-t border-border">
//         <div className="container mx-auto px-4 py-6 flex flex-col sm:flex-row items-center justify-between gap-4">
//           <p className="text-sm text-muted-foreground">
//             © {currentYear} CarMarket. All rights reserved.
//           </p>

//           {/* Social links */}
//           <div className="flex items-center gap-4">
//             {socialLinks.map((social) => (
//               <a
//                 key={social.label}
//                 href={social.href}
//                 aria-label={social.label}
//                 className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-all"
//               >
//                 <social.icon className="h-4 w-4" />
//               </a>
//             ))}
//           </div>
//         </div>
//       </div>
//     </footer>
//   );
// };

// export default Footer;


import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Facebook,
  Twitter,
  Instagram,
  Youtube,
  Mail,
  Phone,
  MapPin,
} from "lucide-react";

const Footer = () => {
  const currentYear = new Date().getFullYear();

  const bgImages = [
    "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1920&h=900&fit=crop&q=80",
    "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1920&h=900&fit=crop&q=80",
    "https://images.unsplash.com/photo-1544636331-e26879cd4d9b?w=1920&h=900&fit=crop&q=80",
  ] as const;

  const bgImage = useMemo(
    () => bgImages[Math.floor(Math.random() * bgImages.length)],
    []
  );

  const footerLinks = {
    company: [
      { label: "About Us", href: "#" },
      { label: "Careers", href: "#" },
      { label: "Press", href: "#" },
      { label: "Blog", href: "#" },
    ],
    support: [
      { label: "Help Center", href: "#" },
      { label: "Contact Us", href: "#" },
      { label: "FAQs", href: "#" },
      { label: "Safety", href: "#" },
    ],
    legal: [
      { label: "Terms of Service", href: "#" },
      { label: "Privacy Policy", href: "#" },
      { label: "Cookie Policy", href: "#" },
      { label: "Accessibility", href: "#" },
    ],
  };

  const socialLinks = [
    { icon: Facebook, href: "#", label: "Facebook" },
    { icon: Twitter, href: "#", label: "Twitter" },
    { icon: Instagram, href: "#", label: "Instagram" },
    { icon: Youtube, href: "#", label: "Youtube" },
  ];

  return (
    <footer className="relative border-t border-border overflow-hidden">
      {/* Outer background image - subtle */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-secondary/50" />
      </div>

      {/* Main footer content */}
      <div className="relative container mx-auto px-4 py-16">
        <div className="relative overflow-hidden rounded-3xl border border-border/40">
          {/* Background image - less blur like hero */}
          <div className="pointer-events-none absolute inset-0" aria-hidden="true">
            <img
              src={bgImage}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover opacity-40 scale-105"
              style={{ objectPosition: "center 40%" }}
            />
            {/* Gradient overlays for text readability */}
            <div className="absolute inset-0 bg-gradient-to-r from-background via-background/70 to-transparent" />
            <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-background/50" />
          </div>

          <div className="relative p-8 md:p-10">
            {/* Brand section */}
            <div className="mb-12">
              <Link to="/" className="inline-block mb-6">
                <span className="text-4xl font-extrabold text-slate-900 font-sansita">
                  Car<span className="text-[#0E317D]">Market</span>
                </span>
              </Link>
              <p className="text-muted-foreground mb-6 whitespace-nowrap leading-relaxed">
                Your trusted destination for luxury and exotic vehicles. We connect
                discerning buyers with premium automobiles from around the world.
              </p>
              <div className="space-y-3">
                <a
                  href="mailto:hello@carmarket.com"
                  className="flex items-center gap-3 text-sm text-muted-foreground hover:text-accent transition-colors"
                >
                  <Mail className="h-4 w-4" />
                  hello@carmarket.com
                </a>
                <a
                  href="tel:+15550123456"
                  className="flex items-center gap-3 text-sm text-muted-foreground hover:text-accent transition-colors"
                >
                  <Phone className="h-4 w-4" />
                  +1 (555) 012-3456
                </a>
                <p className="flex items-center gap-3 text-sm text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  Los Angeles, California
                </p>
              </div>
            </div>

            {/* Links sections - all on same row */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-8">
              <div>
                <h4 className="font-poppins text-sm font-semibold text-foreground uppercase tracking-wider mb-4">
                  Company
                </h4>
                <ul className="space-y-3">
                  {footerLinks.company.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-muted-foreground hover:text-accent transition-colors"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h4 className="font-poppins text-sm font-semibold text-foreground uppercase tracking-wider mb-4">
                  Support
                </h4>
                <ul className="space-y-3">
                  {footerLinks.support.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-muted-foreground hover:text-accent transition-colors"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h4 className="font-poppins text-sm font-semibold text-foreground uppercase tracking-wider mb-4">
                  Legal
                </h4>
                <ul className="space-y-3">
                  {footerLinks.legal.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-muted-foreground hover:text-accent transition-colors"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div className="relative border-t border-border">
        <div className="container mx-auto px-4 py-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">
            © {currentYear} CarMarket. All rights reserved.
          </p>

          {/* Social links */}
          <div className="flex items-center gap-4">
            {socialLinks.map((social) => (
              <a
                key={social.label}
                href={social.href}
                aria-label={social.label}
                className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-all"
              >
                <social.icon className="h-4 w-4" />
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;