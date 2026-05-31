// import { Link } from "react-router-dom";
// import { Button } from "@/components/ui/button";
// import { NavLink } from "@/components/NavLink";
// import { isAuthenticated } from "@/lib/api";

// const Header = () => {
//   const loggedIn = isAuthenticated();

//   return (
//     <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-200 bg-white">
//       <div className="container mx-auto px-4">
//         <div className="flex h-20 items-center justify-between">

//           <div className="flex items-center gap-8">
//             <Link to="/" className="text-2xl font-extrabold text-slate-900 font-sansita">
//               Car<span className="text-[#0E317D]">Market</span>
//             </Link>
//           </div>

//           <nav className="hidden items-center gap-6 md:flex">
//             <NavLink
//               to="/"
//               className="text-base font-semibold text-slate-700 transition-all hover:bg-slate-100 hover:text-slate-900 hover:scale-105 rounded-md px-3 py-2"
//               end
//             >
//               Home
//             </NavLink>
//             <NavLink
//               to="/search"
//               className="text-base font-semibold text-slate-700 transition-all hover:bg-slate-100 hover:text-slate-900 hover:scale-105 rounded-md px-3 py-2"
//             >
//               Browse
//             </NavLink>
//             <NavLink
//               to="/sell"
//               className="text-base font-semibold text-slate-700 transition-all hover:bg-slate-100 hover:text-slate-900 hover:scale-105 rounded-md px-3 py-2"
//             >
//               Sell
//             </NavLink>
//           </nav>

//           <div className="flex items-center gap-2">
//             <Button asChild size="sm" className="rounded-lg bg-[#0E317D] text-white hover:bg-[#0E317D]/90">
//               <Link to={loggedIn ? "/search" : "/login"}>{loggedIn ? "Explore" : "Login"}</Link>
//             </Button>
//           </div>
          
//         </div>
//       </div>
//     </header>
//   );
// };

// export default Header;


import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { NavLink } from "@/components/NavLink";
import { isAuthenticated } from "@/lib/api";

const Header = () => {
  const loggedIn = isAuthenticated();

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-200 bg-white">
      <div className="container mx-auto px-4">
        <div className="flex h-20 items-center justify-between">

          <div className="flex items-center gap-8">
            <Link to="/" className="text-2xl font-extrabold text-slate-900 font-sansita">
              Car<span className="text-[#0E317D]">Market</span>
            </Link>
          </div>

          <nav className="hidden items-center gap-6 md:flex">
            <NavLink
              to="/"
              className="text-base font-semibold text-slate-700 transition-all hover:bg-slate-100 hover:text-slate-900 hover:scale-105 rounded-md px-3 py-2"
              end
            >
              Home
            </NavLink>
            <NavLink
              to="/search"
              className="text-base font-semibold text-slate-700 transition-all hover:bg-slate-100 hover:text-slate-900 hover:scale-105 rounded-md px-3 py-2"
            >
              Browse
            </NavLink>
            <NavLink
              to="/sell"
              className="text-base font-semibold text-slate-700 transition-all hover:bg-slate-100 hover:text-slate-900 hover:scale-105 rounded-md px-3 py-2"
            >
              Sell
            </NavLink>
          </nav>

          <div className="flex items-center gap-2">
            {loggedIn ? (
              <Button asChild size="sm" className="rounded-lg bg-[#0E317D] text-white hover:bg-[#0E317D]/90">
                <Link to="/search">Explore</Link>
              </Button>
            ) : (
              <Link
                to="/login"
                className="relative text-base font-semibold text-slate-700 transition-all duration-200 hover:text-[#0E317D] hover:scale-105 group px-1"
              >
                Login
                <span className="absolute left-0 -bottom-0.5 h-[2px] w-0 bg-[#0E317D] transition-all duration-200 group-hover:w-full rounded-full" />
              </Link>
            )}
          </div>
          
        </div>
      </div>
    </header>
  );
};

export default Header;