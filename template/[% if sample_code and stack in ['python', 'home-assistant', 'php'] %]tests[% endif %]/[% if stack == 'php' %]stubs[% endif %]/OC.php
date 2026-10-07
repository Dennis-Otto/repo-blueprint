<?php

declare(strict_types=1);

/**
 * Minimal stub of the server class through which OCP's App reaches the container of
 * the server. Tests that build the app put their own server into it.
 */

final class OC {
	public static ?object $server = null;
}
