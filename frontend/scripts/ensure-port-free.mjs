import net from "node:net";

const port = Number(process.env.PORT || 3000);
const probe = net.createServer();

probe.once("error", (error) => {
  if (error.code === "EADDRINUSE") {
    console.error(
      `Port ${port} is already in use. Stop the existing NEXORA dev server before starting another or running a build.`,
    );
    process.exit(1);
  }
  console.error(`Could not check port ${port}: ${error.message}`);
  process.exit(1);
});

probe.once("listening", () => probe.close(() => process.exit(0)));
probe.listen(port);
