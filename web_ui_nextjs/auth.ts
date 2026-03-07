import NextAuth from "next-auth";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    MicrosoftEntraID({
      clientId: process.env.AUTH_MICROSOFT_ENTRA_ID_ID,
      clientSecret: process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET,
      issuer: process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER,
      authorization: {
        params: {
          scope: "openid profile email User.Read",
        },
      },
    }),
  ],
  callbacks: {
    // Persist the access_token from the provider into the JWT
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token;
      }
      return token;
    },
    // Expose accessToken to the client-side session object
    async session({ session, token }) {
      session.accessToken = token.accessToken as string;
      return session;
    },
  },
});
