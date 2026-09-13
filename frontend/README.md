# Welcome to your Expo app 👋

This is an [Expo](https://expo.dev) project created with [`create-expo-app`](https://www.npmjs.com/package/create-expo-app).

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npx expo start
   ```

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.


# ENVIRIONMENT VARS --->
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=broadband_solutions

# Auth
JWT_SECRET=change_this_to_a_long_random_secret_in_production

# Demo OTP
DEMO_OTP=123456
DEMO_NUMBERS=9999999996,9999999997,9999999998,9999999999

# AI Chatbot
EMERGENT_LLM_KEY=

# MSG91 SMS (optional — blank rakhoge to mock OTP chalega)
MSG91_AUTH_KEY=
MSG91_TEMPLATE_ID=
MSG91_DLT_TE_ID=

# Optional WATI WhatsApp integration
WATI_API_ENDPOINT=
WATI_API_TOKEN=wati_117317ca-6f04-416b-aad7-e581ef9b72bb.dbYUySWKMyiw-3eSvyqo2VEK0gNMqvx5-flo-LtS5stBdROByFd_fUF4Y1XUrrU00WNyqhdovzp3ncWp1t7MrDsO2LTFaBUKEA8hroPUha7KINj59CLfq9G5qnK7XeER